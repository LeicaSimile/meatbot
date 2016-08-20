import logging
import irc
import lineparser


class MeatBot(irc.IrcBot):

    def on_join(self, msg):
        super(type(self), self).on_join(msg)


def test():
    pass
    

if "__main__" == __name__:
    test()
