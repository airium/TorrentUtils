import pathlib


__all__ = ['TorrentPath']




class TorrentPath(type(pathlib.Path())):

    def isF(self):
        '''Is file (not torrent).'''
        return self.is_file() and self.suffix.lower() != '.torrent'

    def isVF(self):
        '''Is virtual file (not torrent).'''
        return not self.is_dir() and self.suffix.lower() != '.torrent'

    def isT(self):
        '''Is torrent.'''
        return self.is_file() and self.suffix.lower() == '.torrent'

    def isVT(self):
        '''Is virtual torrent.'''
        return not self.is_dir() and self.suffix.lower() == '.torrent'

    def isD(self):
        '''Is directory.'''
        return self.is_dir()

    def isVD(self):
        '''Is virtual directory.'''
        return self.is_dir() or not self.is_file()
