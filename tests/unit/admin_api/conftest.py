"""
Keep Hypothesis's on-disk caches out of the repository tree.

The test gate runs pytest with apps/admin-api as the working directory, so
Hypothesis would otherwise write its constants cache, example database and
unicode data into apps/admin-api/.hypothesis/ on every run. Point the
Hypothesis home directory at a fixed location outside the repository before
any test module is imported. This changes no test behaviour: it is the same
state a fresh CI checkout runs in (no persisted examples between runs).
"""
import os
import tempfile

from hypothesis.configuration import set_hypothesis_home_dir

if not os.environ.get("HYPOTHESIS_STORAGE_DIRECTORY"):
    set_hypothesis_home_dir(os.path.join(tempfile.gettempdir(), "hypothesis-l4"))
