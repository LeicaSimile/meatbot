import logging
import random

import irc
import lineparser

logging.config.fileConfig("logging.ini")
logger = logging.getLogger("irc")

class MeatBot(irc.IrcBot):
    def __init__(self, server, host, port, channels, botnick, realname="", auth="", password=""):
        super(type(self), self).__init__(server, host, port, channels, botnick, realname, auth, password)
        self.database = lineparser.Database(lineparser.FILE_DATABASE)

    def greet(self, nick, channel, msgType="PRIVMSG"):
        """
        Greets the user in the specified channel.

        Args:
            nick(str): The nickname of the person to greet.
            channel(str): The channel to send the greeting.
            msgType(str, optional): Message mode - regular message (PRIVMSG) or whisper (NOTICE).
        """
        greeting = ""
        greetingHeader = "line"
        greetingTable = "phrases"
        
        if random.getrandbits(1):
            phrase1 = self.database.random_line(greetingHeader, greetingTable, {"category_id": "1"})
            phrase2 = self.database.random_line(greetingHeader, greetingTable, {"category_id": "2"})
            greeting = "{a}, {n}. {b}".format(a=phrase1, n=nick, b=phrase2)
        else:
            greeting = self.database.random_line(greetingHeader, greetingTable, {"category_id": "3"})

        greeting = self.substitute(greeting, channel=channel, nick=nick)
        self.say(greeting, channel, msgType)

    def substitute(self, line, channel="", nick=""):
        """
        Finds and performs common substitutions for any phrase the bot will say.

        Args:
            line(str): The phrase to process.
            channel(str, optional): Name of channel that the message is sent to.
            nick(str, optional): Nickname of the user the bot is addressing.
        """
        logger.debug("Line to be processed: {}".format(line))
        
        game = ""
        if channel in self.channels:
            game = str(self.channels[channel].game)
            
        subs = {lineparser.get_setting("Variables", "botnick"): self.botnick,
                lineparser.get_setting("Variables", "channel"): channel,
                lineparser.get_setting("Variables", "game"): game,
                lineparser.get_setting("Variables", "sendnick"): nick,
                lineparser.get_setting("Variables", "owner"): self.owner,}

        line = lineparser.parse_all(lineparser.substitute(line, subs))
        logger.debug("Substitutions performed: {}".format(line))
        
        return line
        
    def on_join(self, msg):
        super(type(self), self).on_join(msg)
        if msg.sender.lower() != self.botnick.lower():
            self.greet(msg.sender, msg.channel)
        

def test():
    pass
    

if "__main__" == __name__:
    test()
