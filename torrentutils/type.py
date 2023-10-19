__all__ = ['strs']

from collections.abc import MutableSequence
from typing import Tuple, Set


strs = MutableSequence[str]|Tuple[str]|Set[str]
