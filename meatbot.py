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

    def disconnect(self, msg=None):
        """
        Disconnect from the server.

        Args:
            msg(str, optional): The quit message. If not specified, the bot will choose a random phrase from the database.
        """
        if msg is None:
            msg = self.database.random_line("line", "phrases", {"category": "9"})
            msg = self.substitute(msg)

        super(type(self), self).disconnect(msg)

    def gossip(self, nick, channel, msgType="PRIVMSG"):
        """
        Makes a remark about the user leaving a channel.

        Args:
            nick(str): The nickname of the person leaving.
            channel(str): The channel the person is leaving.
            msgType(str, optional): Message mode - regular (PRIVMSG) or whisper (NOTICE).
        """
        gossip = ""
        gossip = self.database.random_line("line", "phrases", {"category_id": "5"})
        gossip = self.substitute(gossip, channel=channel, nick=nick)
        
        self.say(gossip, channel, msgType)

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

    def part(self, channel, msg=None):
        if msg is None:
            msg = self.database.random_line("line", "phrases", {"category": "9"})
            msg = self.substitute(msg)

        super(type(self), self).part(channel, msg)

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
        else:
            greeting = ""
            greeting = self.database.random_line("line", "phrases", {"category_id": "8"})
            greeting = self.substitute(greeting, channel=msg.channel)

            self.say(greeting, msg.channel)

    def on_part(self, msg):
        super(type(self), self).on_part(msg)
        if msg.sender.lower() != self.botnick.lower():
            self.gossip(msg.sender, msg.channel)

    def on_quit(self, msg):
        leavernick = msg.sender.lower()

        try:
            leaver = self.server.users[leavernick]
        except KeyError:
            logger.warning("{} was not in {} userlist.".format(leavernick, self.server))
        else:
            for chan in leaver.channels:
                self.gossip(msg.sender, chan)
                self.channels[chan].users.remove(leavernick)
                
            del self.server.users[leavernick]
            

def test():
    pass
    

if "__main__" == __name__:
    test()
