"""What changed in a Notion workspace since a watermark, and where each change sits.

Shared by the `notion-sweep` adapter, the `notion` adapter's default discovery,
and the page-changes tool. One search over Notion's REST API, sorted newest
first and stopped at the watermark, and one placement of each result by its
parent chain against the covered locations the register lists.

**Placement walks the parent chain**, one metadata request per ancestor not yet
seen, cached for the run. A chain that reaches the workspace, or an ancestor the
integration cannot see, is outside every covered location: a covered location is
shared with the integration, and sharing reaches everything beneath it, so a
chain leading into one is visible all the way up to it.

A result whose chain cannot be followed is `Unplaceable`. Every caller treats
that as a gap, because an item that might sit under a covered location must not
be named anywhere.

**Every ancestor is fetched once per run**, whatever asks about it. The chain is
held by `Ancestry`, which the covered placement walks first and the reading rules
(`notion_page_changes.ReadingRules`) walk again for the pages outside, so the
second walk is a run of cache hits. The reading rules ask only for a page's
`lineage`, which ends quietly where an ancestor cannot be fetched: a rule that
cannot be placed is not applied, and the page is read whole.
"""

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
    """Every item's parent, fetched at most once per run. An ancestor the
    integration cannot see is remembered as None, the top of the visible tree."""

    def __init__(self, notion):
        self.notion = notion
        self.parents = {}

    def parent_of(self, item):
        """The item's parent, or None at the top of the visible tree. A fetch that
        fails for any reason but 404 raises, and is not remembered."""
        parent = item.get("parent") or {}
        kind = parent.get("type")

        if kind not in PARENT_KINDS:
            return None

        identifier = normalize(parent[kind])

        if identifier not in self.parents:
            self.parents[identifier] = self.fetch_visible(kind, parent[kind])

        return self.parents[identifier]

    def fetch_visible(self, kind, identifier):
        try:
            return self.fetch(kind, identifier)

        except ExportError as error:
            if error.status == 404:
                return None

            raise

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


class Placement:
    """Which covered location, if any, each item sits under, cached per run."""

    def __init__(self, notion, locations, ancestry=None):
        self.ancestry = ancestry or Ancestry(notion)
        self.locations = {normalize(location["id"]): location["name"] for location in locations}
        self.known = {}

    def location_of(self, item):
        """The covered location's name, or None when the item is outside all of them."""
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
                raise Unplaceable(str(error)) from None

            if current is None:
                return self.settle(chain, None)

        raise Unplaceable(f"a parent chain longer than {MAX_ANCESTRY} items")

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
    """The search results, sorted by where they sit."""

    def __init__(self):
        self.outside = []
        self.under = {}
        self.unplaced = 0

    def add(self, item, location):
        if location is None:
            self.outside.append(item)

        else:
            self.under.setdefault(location, []).append(item)

    def count_under(self, location):
        return len(self.under.get(location, []))


def changes_since(notion, locations, since, gaps, ancestry=None):
    """Every item edited since the watermark, placed against the covered locations.
    An item that cannot be placed is counted and reported as a gap, never kept.
    Pass the run's `ancestry` to reuse what this placement fetched."""
    placement = Placement(notion, locations, ancestry)
    changes = Changes()

    for item in search_since(notion, since, gaps):
        try:
            changes.add(item, placement.location_of(item))

        except Unplaceable as error:
            changes.unplaced += 1
            gaps.add(f"item {item['id']} could not be placed: {error}")

    return changes


def read_locations(source):
    locations = source.get("covered_locations") or []

    if not locations:
        raise configuration.ConfigurationError(
            'the source lists no "covered_locations", so there is nothing to export. A run '
            "that walks nothing would report a quiet source it never looked at."
        )

    for location in locations:
        if not isinstance(location, dict) or not location.get("id") or not location.get("name"):
            raise configuration.ConfigurationError(
                'every entry in "covered_locations" needs a "name" and an "id"'
            )

    return locations


def covered_locations(source):
    """The locations a source excludes, and the name of the source whose adapter
    reads them."""
    if "covered_by" in source:
        name = source["covered_by"]

        return read_locations(configuration.source(name)), name

    if "covered_locations" in source:
        return source["covered_locations"], "the notion adapter"

    raise configuration.ConfigurationError(
        'the source names no "covered_by" source and lists no "covered_locations". A '
        "sweep with nothing to exclude writes every title in the workspace, record-dense "
        'locations included; list them, or give "covered_locations": [] to mean none.'
    )
