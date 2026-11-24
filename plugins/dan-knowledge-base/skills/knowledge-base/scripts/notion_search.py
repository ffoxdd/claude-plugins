"""What changed in a Notion workspace since a watermark, and where each change sits.

Shared by the `notion-sweep` adapter, the `notion` adapter's default discovery,
and the page-changes tool. One search over Notion's REST API, sorted newest
first and stopped at the time it is given, and one placement of each result by
its parent chain against the locations the register lists. The adapters give it
their lookback floor rather than the watermark (`notion_ledger.py`).

**The register lists two kinds of location**, side by side on the source that
holds them:

    "covered_locations": [{"name": "Operations hub", "id": "<page id>"}],
    "open_locations":    [{"name": "Engineering wiki", "id": "<page id>"}]

A page under a covered location is never read by the sweep; the `notion` adapter
exports it for a covered gate. Without `open_locations`, every other page is
readable. With it, the register is default-deny: only a page under an open
location is readable, and a page under neither list is handled exactly as a
covered one is, counted, named by id and exported by the `notion` adapter. An
open location nested under a covered one, or the reverse, resolves to the nearest
listed ancestor; an id listed as both is covered.

**Placement walks the parent chain**, one metadata request per ancestor not yet
seen, cached for the run, and stops at the first listed location. A chain that
reaches the workspace is under no listed location. A chain that meets a
listed location stops there, whatever lies above it. A chain that meets an
ancestor which cannot be fetched first is `Unplaceable`: what lies above it
might be a covered location, so the item is under no location anyone can vouch
for. One kind of unseen ancestor is the top of the tree instead, as the
workspace is: a 404 in a source that lists no open location, once the run has
confirmed its token can fetch every covered location. Sharing reaches everything
beneath a page, so a covered location this token can see cannot sit above a
page it cannot, and the 404 hides nothing; the confirmation is asked once a
run, on the first 404. A covered location the token cannot fetch, or any open
location listed, keeps the 404 unplaceable; listing the page the integration is
shared at then ends the walk before it reaches the ancestor it cannot see.

Every caller treats an unplaceable item as a gap, and writes nothing of it but
its id, because an item that might sit under a covered location must not be
named anywhere.

**Every ancestor is fetched once per run**, whatever asks about it. The chain is
held by `Ancestry`, which the covered placement walks first and the reading rules
(`notion_page_changes.ReadingRules`) walk again for the pages outside, so the
second walk is a run of cache hits. The reading rules ask only for a page's
`lineage`, which ends quietly where an ancestor cannot be fetched: a rule that
cannot be placed is not applied, and the page is read whole.
"""

from dataclasses import dataclass

import configuration
from notion_api import PAGE_SIZE, ExportError, edited_since

# Deeper than any real workspace nests; a chain this long is a cycle or a defect.
MAX_ANCESTRY = 64

# The parent types that name another item, and the call that fetches each.
PARENT_KINDS = ("page_id", "database_id", "block_id")


class Unplaceable(Exception):
    """A result whose parent chain could not be followed."""


def normalize(identifier):
    return identifier.replace("-", "").lower()


class Ancestry:
    """Every item's parent, fetched at most once per run."""

    def __init__(self, notion):
        self.notion = notion
        self.parents = {}
        self.unseen = {}

    def parent_of(self, item):
        """The item's parent, or None when the item sits at the top of the
        workspace. A fetch that fails raises; a 404 is remembered and raised again
        for every item under it, since it fails the same way all run."""
        parent = item.get("parent") or {}
        kind = parent.get("type")

        if kind not in PARENT_KINDS:
            return None

        identifier = normalize(parent[kind])

        if identifier in self.unseen:
            raise self.unseen[identifier]

        if identifier not in self.parents:
            self.parents[identifier] = self.fetch_remembering_unseen(kind, parent[kind])

        return self.parents[identifier]

    def fetch_remembering_unseen(self, kind, identifier):
        try:
            return self.fetch(kind, identifier)

        except ExportError as error:
            if error.status == 404:
                self.unseen[normalize(identifier)] = error

            raise

    def remembered(self, kind, identifier):
        """The item, fetched at most once a run, so a location confirmed reachable
        costs nothing more when a chain later passes through it."""
        normalized = normalize(identifier)

        if normalized not in self.parents:
            self.parents[normalized] = self.fetch(kind, identifier)

        return self.parents[normalized]

    def fetch(self, kind, identifier):
        if kind == "page_id":
            return self.notion.page(identifier)

        if kind == "database_id":
            return self.notion.database(identifier)

        return self.notion.block(identifier)

    def lineage(self, item):
        """The item's id and its ancestors', nearest first, as far up as the chain
        can be followed."""
        identifiers = []
        current = item

        while current is not None and len(identifiers) < MAX_ANCESTRY:
            identifiers.append(normalize(current["id"]))

            try:
                current = self.parent_of(current)

            except ExportError:
                break

        return identifiers


@dataclass(frozen=True)
class Location:
    """A location the register lists, and whether it is covered or open."""
    name: str
    covered: bool


class Placement:
    """Which listed location, if any, each item sits under, cached per run."""

    def __init__(self, notion, locations, ancestry=None, open_locations=None):
        self.ancestry = ancestry or Ancestry(notion)
        self.locations = {normalize(location["id"]): Location(location["name"], False)
                          for location in open_locations or []}
        self.locations.update({normalize(location["id"]): Location(location["name"], True)
                               for location in locations})
        self.covered = list(locations)
        self.opened = open_locations is not None
        self.covered_confirmed = None
        self.known = {}

    def location_of(self, item):
        """The nearest listed Location at or above the item, or None when the
        chain reaches the top of the workspace without meeting one. A listed
        location met on the way up places the item whatever lies above it, and
        an ancestor the integration cannot see (404) ends the chain at None when
        it can hide nothing (`unseen_is_top`)."""
        chain = []
        current = item

        for _ in range(MAX_ANCESTRY):
            identifier = normalize(current["id"])

            if identifier in self.known:
                return self.settle(chain, self.known[identifier])

            chain.append(identifier)

            if identifier in self.locations:
                return self.settle(chain, self.locations[identifier])

            try:
                current = self.ancestry.parent_of(current)

            except ExportError as error:
                if error.status == 404 and self.unseen_is_top():
                    return self.settle(chain, None)

                raise Unplaceable(str(error)) from None

            if current is None:
                return self.settle(chain, None)

        raise Unplaceable(f"a parent chain longer than {MAX_ANCESTRY} items")

    def unseen_is_top(self):
        """Whether an ancestor the integration cannot see can only lie above every
        listed location: when nothing is listed, or when no open location is and
        this token can fetch every covered one. Confirmed once a run."""
        if not self.locations:
            return True

        if self.opened:
            return False

        if self.covered_confirmed is None:
            self.covered_confirmed = all(map(self.fetchable, self.covered))

        return self.covered_confirmed

    def fetchable(self, location):
        kinds = ("database_id",) if location.get("kind") == "database" \
            else ("page_id", "database_id")

        for kind in kinds:
            try:
                self.ancestry.remembered(kind, location["id"])

                return True

            except ExportError:
                continue

        return False

    def settle(self, chain, location):
        for identifier in chain:
            self.known[identifier] = location

        return location


def search_since(notion, since, gaps):
    """Every search result edited at or after the watermark, newest first."""
    body = {"sort": {"direction": "descending", "timestamp": "last_edited_time"},
            "page_size": PAGE_SIZE}

    while True:
        try:
            result = notion.request("POST", "/search", body)

        except ExportError as error:
            gaps.add(f"a search page could not be read: {error}")

            return

        items = result.get("results") or []
        yield from (item for item in items if edited_since(item, since))

        if not result.get("has_more") or not items or not edited_since(items[-1], since):
            return

        body = {**body, "start_cursor": result.get("next_cursor")}


class Changes:
    """The search results, sorted by where they sit: `readable`, whose content a
    session may read; `under`, by covered location; `unlisted`, under no listed
    location in a register that names open locations, and so handled as covered;
    and `unplaced`, whose chain could not be followed."""

    def __init__(self, default_deny=False):
        self.default_deny = default_deny
        self.readable = []
        self.under = {}
        self.unlisted = []
        self.unplaced = []

    def add(self, item, location):
        if location is None:
            (self.unlisted if self.default_deny else self.readable).append(item)

        elif location.covered:
            self.under.setdefault(location.name, []).append(item)

        else:
            self.readable.append(item)

    def count_under(self, location):
        return len(self.under.get(location, []))


def changes_since(notion, locations, since, gaps, ancestry=None, open_locations=None):
    """Every item edited since the watermark, placed against the listed locations;
    `open_locations`, when not None, makes the placement default-deny. An item
    that cannot be placed is kept by id only and reported as a gap. Pass the run's
    `ancestry` to reuse what this placement fetched."""
    placement = Placement(notion, locations, ancestry, open_locations)
    changes = Changes(default_deny=open_locations is not None)

    for item in search_since(notion, since, gaps):
        try:
            changes.add(item, placement.location_of(item))

        except Unplaceable as error:
            changes.unplaced.append(item)
            gaps.add(f"item {item['id']} could not be placed: {error}; list the page the "
                     "integration is shared at as an open or covered location")

    return changes


def validated(locations, key):
    if not isinstance(locations, list):
        raise configuration.ConfigurationError(f'"{key}" must be a list of locations')

    for location in locations:
        if not isinstance(location, dict) or not location.get("id") or not location.get("name"):
            raise configuration.ConfigurationError(
                f'every entry in "{key}" needs a "name" and an "id"'
            )

    return locations


def open_locations(source):
    """The source's open locations, or None when it names none and every page
    outside a covered location is readable. An empty list is default-deny with
    nothing open."""
    if "open_locations" not in source:
        return None

    return validated(source["open_locations"], "open_locations")


def read_locations(source):
    """The covered locations of the source the `notion` adapter reads. One that
    lists none is refused unless it names open locations, whose complement it
    then exports."""
    locations = source.get("covered_locations") or []

    if not locations and open_locations(source) is None:
        raise configuration.ConfigurationError(
            'the source lists no "covered_locations", so there is nothing to export. A run '
            "that walks nothing would report a quiet source it never looked at."
        )

    return validated(locations, "covered_locations")


@dataclass(frozen=True)
class Listing:
    """What a source lists: its covered locations, its open locations (None when
    it names none), and the name of the source whose adapter reads what is not
    readable."""
    covered: list
    open: list
    reader: str


def listed_locations(source):
    """The locations a sweep places against. Both lists live on one source: the
    one `covered_by` names, or the sweep's own when it lists `covered_locations`."""
    if "covered_by" in source:
        name = source["covered_by"]
        covered_source = configuration.source(name)

        return Listing(read_locations(covered_source), open_locations(covered_source), name)

    if "covered_locations" in source:
        return Listing(validated(source["covered_locations"], "covered_locations"),
                       open_locations(source), "the notion adapter")

    raise configuration.ConfigurationError(
        'the source names no "covered_by" source and lists no "covered_locations". A '
        "sweep with nothing to exclude writes every title in the workspace, record-dense "
        'locations included; list them, or give "covered_locations": [] to mean none.'
    )
