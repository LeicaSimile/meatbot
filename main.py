import irc


class MeatBot(irc.IrcBot):
    def __init__(self, configFile="config.ini"):
        pass

    def join(self, channel, msg=""):
        pass

    def update(self, files=None):
        """ Reads files again. """
        if files:
            ## Read those in the list only.
            pass
        else:
            ## Read all files.
            pass


def main():
    pass

if "__main__" == __name__:
    main()
