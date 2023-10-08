class TorrentNotReady(Exception):
    pass




class PieceSizeTooSmall(ValueError):
    pass




class PieceSizeTooLarge(ValueError):
    pass




class PieceSizeUncommon(ValueError):
    pass




class EmptySourceSize(ValueError):
    pass




class TorrentIsEmptyError(ValueError):
    pass