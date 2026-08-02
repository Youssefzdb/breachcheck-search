#!/usr/bin/env python3
"""
HTTP Range File - makes a remote SquashFS file accessible via seek/read
using HTTP Range requests. Only downloads what's needed.
"""

import requests
import time
from io import BytesIO

class HttpRangeFile:
    """File-like object that reads from HTTP server using Range requests."""
    
    def __init__(self, url, block_size=1024*1024, cache_size=50):
        self.url = url
        self.block_size = block_size  # 1MB blocks
        self.pos = 0
        self.size = 0
        self.cache = {}  # block_idx -> bytes
        self.cache_order = []
        self.max_cache = cache_size  # cache up to 50MB
        
        # Get file size
        resp = requests.head(url, timeout=30)
        self.size = int(resp.headers.get('content-length', 0))
        
    def seekable(self):
        return True
    
    def seek(self, offset, whence=0):
        if whence == 0:
            self.pos = offset
        elif whence == 1:
            self.pos += offset
        elif whence == 2:
            self.pos = self.size + offset
        return self.pos
    
    def tell(self):
        return self.pos
    
    def read(self, size=-1):
        if size == -1:
            size = self.size - self.pos
        if size == 0:
            return b''
        if self.pos >= self.size:
            return b''
        
        end = min(self.pos + size, self.size)
        data = self._read_range(self.pos, end)
        self.pos = end
        return data
    
    def _read_range(self, start, end):
        """Read bytes [start, end) using HTTP Range, with block caching."""
        result = bytearray()
        pos = start
        
        while pos < end:
            block_idx = pos // self.block_size
            block_start = block_idx * self.block_size
            block_end = min(block_start + self.block_size, self.size)
            
            # Get block (from cache or download)
            if block_idx not in self.cache:
                self._download_block(block_idx)
            
            block_data = self.cache[block_idx]
            offset_in_block = pos - block_start
            bytes_to_read = min(block_end - pos, end - pos)
            
            result.extend(block_data[offset_in_block:offset_in_block + bytes_to_read])
            pos += bytes_to_read
        
        return bytes(result)
    
    def _download_block(self, block_idx):
        """Download a block via HTTP Range request."""
        start = block_idx * self.block_size
        end = min(start + self.block_size - 1, self.size - 1)
        
        headers = {'Range': f'bytes={start}-{end}'}
        
        for attempt in range(3):
            try:
                resp = requests.get(self.url, headers=headers, timeout=60)
                if resp.status_code == 206 or resp.status_code == 200:
                    data = resp.content
                    self.cache[block_idx] = data
                    
                    # Manage cache
                    self.cache_order.append(block_idx)
                    if len(self.cache_order) > self.max_cache:
                        old = self.cache_order.pop(0)
                        if old != block_idx:
                            self.cache.pop(old, None)
                    
                    return
            except Exception as e:
                if attempt < 2:
                    time.sleep(2)
                else:
                    raise
        
        raise Exception(f"Failed to download block {block_idx}")
    
    def close(self):
        self.cache.clear()


if __name__ == "__main__":
    url = 'https://ia600706.us.archive.org/20/items/2019-collection-1-5-antipublic-tri-pack-squashfs/Collection_%231-%235_Antipublic_tri-pack.squashfs'
    
    print("Testing HttpRangeFile...")
    f = HttpRangeFile(url, block_size=2*1024*1024)  # 2MB blocks
    print(f"File size: {f.size / 1024**3:.2f} GB")
    
    # Try to read SquashFS
    from dissect.squashfs import SquashFS
    
    print("Opening SquashFS...")
    sqfs = SquashFS(f)
    print(f"Block size: {sqfs.block_size}")
    print(f"Compression: {sqfs.compression}")
    
    # List root directory
    print("\nRoot directory:")
    for entry in sqfs.root.entries():
        print(f"  {entry.name} ({entry.inode.size if hasattr(entry, 'inode') else '?'})")
    
    f.close()
