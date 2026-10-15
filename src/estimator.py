# GeneanetForGramps - Estimate how far along a tree traversal is.
#
# Standalone (no Gramps imports) so it can be unit-tested on its own.
#
# The size of the tree is unknown until it has been walked, so the estimate is
# built from what has been seen: every page parsed reveals links to further
# pages ("discovered"), and the number of links followed per page so far (the
# observed fan-out) is used to project how much each still-unvisited page is
# going to add before the requested depth limit is reached.


class TreeEstimator:

    # Observed fan-out is clamped: a couple of well-documented early pages
    # must not make the projection explode (2.5**depth grows very fast).
    FAN_OUT_LIMIT = 2.5
    # Never show 100% before the traversal is actually over.
    MAX_RUNNING_FRACTION = 0.99
    MAX_PROJECTED_PAGES = 1000000

    def __init__(self, max_level):
        self.max_level = max_level
        self.tree_size = None  # persons in the whole tree, when known
        self.done = 0
        self._visited = set()
        self._pending = {}  # url -> level it will be fetched at
        self._expanding_pages = 0  # pages that could still lead further
        self._links_found = 0
        self._fraction = 0.0

    def page_done(self, url, level, discovered):
        """Record a fetched page. `discovered` is a list of (url, level) for
        the links on it that the traversal is going to follow."""
        self.done += 1
        self._visited.add(url)
        self._pending.pop(url, None)
        if level < self.max_level:
            self._expanding_pages += 1
            self._links_found += len(discovered)
        for link, link_level in discovered:
            if link and link not in self._visited and link not in self._pending:
                self._pending[link] = link_level

    def _fan_out(self):
        if not self._expanding_pages:
            return 1.0
        return min(self._links_found / self._expanding_pages, self.FAN_OUT_LIMIT)

    def set_tree_size(self, size):
        """The number of persons of the whole tree: no import can fetch more
        pages than that, so it caps the projection."""
        self.tree_size = size if size and size > 0 else None

    def _projected(self):
        """Pages still to fetch, from the links seen and the depth limit."""
        fan = self._fan_out()
        total = 0.0
        for level in self._pending.values():
            total += 1.0
            for k in range(1, max(0, self.max_level - level) + 1):
                total += fan ** k
                if total > self.MAX_PROJECTED_PAGES:
                    return float(self.MAX_PROJECTED_PAGES)
        return total

    def remaining(self):
        """Estimated number of pages still to fetch."""
        projected = self._projected()
        if self.tree_size is not None:
            projected = min(projected, max(self.tree_size - self.done, 0))
        return projected

    def capped(self):
        """True when the tree size, not the projection, sets the total."""
        return (self.tree_size is not None
                and self.done + self._projected() > self.tree_size)

    def total(self):
        return self.done + self.remaining()

    def fraction(self):
        """Progress in [0, 0.99]. Never goes backwards: discovering that the
        tree is bigger than guessed makes the bar wait, not retreat."""
        total = self.total()
        if self.done and total:
            raw = self.done / total
            self._fraction = max(self._fraction, min(raw, self.MAX_RUNNING_FRACTION))
        return self._fraction
