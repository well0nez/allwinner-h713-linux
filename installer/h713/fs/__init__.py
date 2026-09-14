# -*- coding: utf-8 -*-
"""Filesystem readers of the h713 package: FAT12/16/32, LP ("super"), ext4, Android sparse."""

from __future__ import annotations

from h713.fs.ext4 import Ext4, Ext4Base, Ext4Debugfs
from h713.fs.fat16 import Fat
from h713.fs.lpsuper import LpSuper
from h713.fs.sparse import SPARSE_MAGIC, SparseSource, is_sparse, write_sparse

__all__ = ["Ext4", "Ext4Base", "Ext4Debugfs", "Fat", "LpSuper",
           "SPARSE_MAGIC", "SparseSource", "is_sparse", "write_sparse"]
