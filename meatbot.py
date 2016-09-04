# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import logging
import random
import re

import irc
import lineparser

logging.config.fileConfig("logging.ini")
logger = logging.getLogger("irc")

try:
    unicode  # Python 2
except NameError:
    unicode = str  # Python 3

class MeatBot(irc.IrcBot):
    def __init__(self, server, host, port, channels, botnick, realname="", auth="", password=""):
        super(type(self), self).__init__(server, host, port, channels, botnick, realname, auth, password)
        self.database = lineparser.Database(lineparser.FILE_DATABASE)

    def alert(self):
        """
        Notify about an event or message.
        """
        pass

    def chat(self, msg, msgType="PRIVMSG"):
        """
        Respond to the bot's name being called.

        Args:
            msg(IrcMessage): Message with the bot's name.
            msgType(unicode, optional): Type of message sent - default (PRIVMSG) or whisper (NOTICE).
                The bot will use the same message type when responding.
        """
        chatTable = "phrases"
        responseId = "6"

        if msg.message.startswith("\001ACTION"):
##            if random.randrange(0, 100) <= 90:  # 90% chance of responding with a /me (ACTION) phrase.
                responseId = "7"
                msgType = "PRIVMSG"
        else:
            if random.randrange(0, 100) <= 10:  # 10% chance of responding with a /me (ACTION) phrase.
                responseId = "7"
                msgType = "PRIVMSG"
        
        phrase = self.database.random_line("line", chatTable, {"category_id": responseId})
        phrase = self.substitute(phrase, channel=msg.channel, nick=msg.sender)
        
        self.say(phrase, msg.channel, msgType)
        
    def check_triggers(self, msg, msgType="PRIVMSG"):
        """
        Check a message for any triggers the bot may react to. Returns True if a trigger was found.

        Args:
            msg(IrcMessage): Message to examine.
            msgType(unicode, optional): Type of message to examine - default (PRIVMSG) or whisper (NOTICE).
                The bot will use the same message type when reacting to the trigger.
        """
        triggerTable = "triggers"
        
        for i in self.database.get_ids(triggerTable):
            trigger = self.database.get_field(i, "trigger", triggerTable)
            
            if not self.database.get_field(i, "case_sensitive", triggerTable):
                trigger = re.compile(trigger, flags=re.I)
            else:
                trigger = re.compile(trigger)

            try:
                chance = self.database.get_field(i, "chance", triggerTable)
                chance = float(chance)
            except TypeError:
                logger.warning("How could I make a float out of {}?".format(chance))
            else:
                if trigger.search(msg.message) and random.randrange(0, 100) <= chance:
                    reaction = self.database.get_field(i, "reaction", triggerTable)
                    self.say(reaction, msg.channel, msgType)

                    if self.database.get_field(i, "alert", triggerTable):
                        self.alert()

                    return True

    def disconnect(self, msg=None):
        """
        Disconnect from the server.

        Args:
            msg(unicode, optional): The quit message. If not specified, the bot will choose a random phrase from the database.
        """
        if msg is None:
            msg = self.database.random_line("line", "phrases", {"category": "9"})
            msg = self.substitute(msg)

        super(type(self), self).disconnect(msg)

    def gossip(self, nick, channel, msgType="PRIVMSG"):
        """
        Makes a remark about the user leaving a channel.

        Args:
            nick(unicode): The nickname of the person leaving.
            channel(unicode): The channel the person is leaving.
            msgType(unicode, optional): Message mode - regular (PRIVMSG) or whisper (NOTICE).
        """
        gossip = ""
        gossip = self.database.random_line("line", "phrases", {"category_id": "5"})
        gossip = self.substitute(gossip, channel=channel, nick=nick)
        
        self.say(gossip, channel, msgType)

    def greet(self, nick, channel, msgType="PRIVMSG"):
        """
        Greets the user in the specified channel.

        Args:
            nick(unicode): The nickname of the person to greet.
            channel(unicode): The channel to send the greeting.
            msgType(unicode, optional): Message mode - regular message (PRIVMSG) or whisper (NOTICE).
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
        """
        Leave a channel.

        Args:
            channel(unicode): The channel to leave.
            msg(unicode, optional): The part message. If not specified, the bot will choose a random phrase from the database.
        """
        if msg is None:
            msg = self.database.random_line("line", "phrases", {"category": "9"})
            msg = self.substitute(msg)

        super(type(self), self).part(channel, msg)

    def process_message(self, msg, msgType="PRIVMSG"):
        """
        Check a message (PRIVMSG/NOTICE) for commands and other things to react to.

        Args:
            msg(IrcMessage): The message to process.
            msgType(unicode): Type of message to process - default (PRIVMSG) or whisper (NOTICE).
        """
        msgLower = msg.message.lower().strip()
        
        if re.match(r"{}\b".format(lineparser.get_setting("Commands", "quiet")), msgLower, flags=re.I):
            if self.quiet(msg):
                ## Someone wants the bot to stop speaking.
                return
            
        if self.check_triggers(msg):
            return
        
        if re.search(r"\b(?:{})+\b".format(self.botnick), msg.message, flags=re.I):
            ## Someone said the bot's name.
            logger.debug("Bot name mentioned: {}".format(msg.message))
            self.chat(msg, msgType)

    def quiet(self, msg):
        """
        Tells the bot to not say anything in a channel or to speak freely again.

        Args:
            msg(IrcMessage): The message to process.
        """
        msgLower = msg.message.lower()
        chanLower = msg.channel.lower()
        alreadyQuietMsg = ("I was already told to keep my trap shut in {}. ".format(msg.channel)
                           "Say '{} off' there to let me speak again.".format(lineparser.get_setting("Commands", "quiet")))

        if "off" in msgLower.split():
            self.channels[chanLower].quiet = False
        elif self.channels[chanLower].quiet:
            ## Bot was already told to be quiet.
            self.say(alreadyQuietMsg, msg.sender, msgType="NOTICE")
        else:
            self.channels[chanLower].quiet = True

        return self.channels[chanLower].quiet

    def substitute(self, line, channel="", nick=""):
        """
        Finds and performs common substitutions for any phrase the bot will say.

        Args:
            line(unicode): The phrase to process.
            channel(unicode, optional): Name of channel that the message is sent to.
            nick(unicode, optional): Nickname of the user the bot is addressing.
        """
        logger.debug("Line to be processed: {}".format(line))
        
        game = ""
        if channel in self.channels:
            game = unicode(self.channels[channel].game, "utf-8")
            
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

    def on_notice(self, msg):
        super(type(self), self).on_notice(msg)
        self.process_message(msg, "NOTICE")

    def on_part(self, msg):
        super(type(self), self).on_part(msg)
        if msg.sender.lower() != self.botnick.lower():
            self.gossip(msg.sender, msg.channel)

    def on_privmsg(self, msg):
        super(type(self), self).on_privmsg(msg)
        self.process_message(msg, "PRIVMSG")

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
