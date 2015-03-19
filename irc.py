import re
import os.path
import logging
import traceback
import random
from random import getrandbits
import socket
import time
from time import strftime
from datetime import timedelta
import threading
import Queue
import urllib2

import lineparser
from lineparser import DIR_DATABASE, DIR_LOG
from games import HijackGame
from bs4 import BeautifulSoup


THREAD_MIN = 15
FILE_CHATLINES = "chat"
FILE_SUBJECTS = "subjects"
FILE_USERS = "users"
OP = "o"
HALF_OP = "h"
VOICED = "v"
ALL = "*"


#### ---- IRC Stuff ---- ####
class IrcMessage(object):
    """
    For parsing IRC messages.
    """
    def __init__(self, message, timestamp=None):
        self.command = ""
        self.parameters = ""
        self.rawMsg = message
        self.sender = ""
        if not timestamp:
            self.timestamp = time.time()
        else:
            self.timestamp = timestamp
        self.basic_parse()

    def basic_parse(self):
        """
        Identify basic properties of message (sender and command).
        """
        message = self.rawMsg.strip()
        matchUserMsg = re.match(r":(\S+)!\S+ (\w+) ", message)
        matchServerMsg = re.match(r":(\S+) (\S+) ", message)
        matched = ""

        if matchUserMsg:
            self.sender = matchUserMsg.group(1)
            self.command = matchUserMsg.group(2)
            matched = matchUserMsg.group(0)
        else:  # Server message.
            if data.startswith("PING "):
                self.command = "PING"
                matched = "PING "
            elif matchServerMsg:
                self.sender = matchServerMsg.group(1)
                self.command = matchServerMsg.group(2)
                matched = matchServerMsg.group(0)
        try:
            self.parameters = message.split(matched)[1]
        except IndexError:
            pass
        

class IrcBot(threading.Thread):
    def __init__ (self, host, port, channels, botnick, realname="", auth="", password=""):
        self.host = host
        self.port = port
        self.botnick = botnick

        if not auth:
            self.auth = self.botnick
            
        self.password = password
        self.username = self.botnick

        self.variables = lineparser.Settings().keywords
        self.channels = {}
        for chan in channels:
            self.init_channel(chan)

        self.realname = realname
        self.init_channel(self.botnick)
        
        self.dataThreads = []
        self.queue = Queue.Queue()
        self.timeGotData = time.time()
        
        threading.Thread.__init__(self)

    def run(self):
        channels = [chan for chan in self.channels]
        self.__init__(self.host, self.port, channels, self.botnick, self.realname, self.auth, self.password)
        
        ## Try to connect to server.
        try:
            self.irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except:
            print("Failed to create socket.")
            return

        self.remoteIP = socket.gethostbyname(self.host)
        print(self.remoteIP)

        self.irc.connect((remoteIP, self.port))
        
        self.nick_change("NICK {}\r\n".format(self.botnick))
        self.raw_send("USER {} {} {} :{}\r\n".format(self.username, self.host, self.host, self.realname))

        while True:
            try:
                while len(self.dataThreads) < (len(self.channels) + THREAD_MIN):
                    p = threading.Thread(target=self.dataProcessor)
                    p.start()
                    self.dataThreads.append(p)
                
                self.get_data()
                if 200 < time.time() - self.timeGotData:
                    ## 200+ seconds passed since last message. Try reconnecting.
                    self.run()
            except IOError as ex:
                print("IO Error encountered: {}".format(str(ex.args)))
            except socket.timeout:
                print("The socket timed out. Trying a connection after 15 seconds.")
                time.sleep(15)
                
                ## Try again.
                self.run()
            finally:
                time.sleep(0.5)

    def act(self, action, channel):
        if "#" in channel:
            if self.channels[channel.lower()]["quiet"]:
                return
        if channel.lower() == self.botnick.lower():
            return
            
        ## The bot sends an action ("/me" message).
        sendMsg = "PRIVMSG {chan} :\001ACTION {act}\001\r\n".format(chan=channel, act=action)
        self.raw_send(sendMsg)

    def alert(self, message):
        pass

    def ask_time(self, server = ""):
        self.raw_send("TIME {s}\r\n".format(s = server))

    def colour_strip(text):
        return re.sub(r"\x03\d+", "", text)

    def disconnect(self, msg=":("):
        self.raw_send("QUIT :{msg}\r\n".format(msg=msg))

    def get_auth(self, user):
        self.whois(user)
        
    def get_data(self):
        self.irc.setblocking(0)  # Non-blocking.
        try:
            data = self.irc.recv(4096)
        except socket.error:
            return

        data = self.colour_strip(data)  # Might disable when the bot has a better GUI.
        data = data.splitlines()
        
        for line in data:
            if line.strip():
                self.prettify_line(line)
                self.timeGotData = time.time()
            dataProcess = threading.Thread(target=self.process_data, args=(line,))
            dataProcess.start()

        return

    def identify(self, service="NickServ", command="IDENTIFY"):
        self.say(" ".join([command, self.auth, self.password]), service,
                 output=" ".join([command, self.auth, "*".rjust(len(self.password), "*")]))

    def init_channel(self, channel):
        self.channels[channel.lower()] = Channel(channel)
            
    def join(self, data, nick, channel, msg=""):
        if channel.lower() != self.botnick.lower() and "#" in channel:
            sendMsg = "JOIN {}\r\n".format(channel)
            if channel.lower() not in self.channels:
                self.init_channel(channel)

            self.raw_send(sendMsg)
            self.prettify_line(":{}!{} {}".format(self.botnick, self.remoteIP, sendMsg))
        return
                
    def mode(self, param1, param2="", param3=""):
        sendMsg = " ".join(("MODE", param1, param2, param3)).strip()
        sendMsg = "{}\r\n".format(sendMsg)
        self.raw_send(sendMsg)
        self.prettify_line(":{}!{} {}".format(self.botnick, self.remoteIP, sendMsg))
        
    def nick_change(self, nick):
        sendMsg = "NICK {nick}\r\n".format(nick=nick)
        self.raw_send(sendMsg)

        ## TODO: Verify nickchange was successful.
        self.prettify_line(":{}!{} {}".format(self.botnick, self.remoteIP, sendMsg))
        self.botnick = nick

    def part(self, channel, msg=""):
        try:
            del self.channels[channel.lower()]
            sendMsg = "PART {chan} :{msg}\r\n".format(chan=channel, msg=msg)
            self.raw_send(sendMsg)
            self.prettify_line(":{}!{} {}".format(self.botnick, self.remoteIP, sendMsg))
        except KeyError:
            pass

    def prettify_line(self, line):
        line = line.strip()
        joined = re.match(r":(\S+)!\S+ JOIN (#\S+)$", line)
        kicked = re.match(r":(\S+)!\S+ KICK (#\S+) (\S+) :(.+)", line)
        parted = re.match(r":(\S+)!\S+ PART (#\S+)$", line)
        quitted = re.match(r":(\S+)!\S+ QUIT(.*)", line)
        msged = re.match(r":(\S+)!\S+ PRIVMSG (\S+) :(.+)", line)
        nickChanged = re.match(r":(\S+)!\S+ NICK :(\S+)", line)
        noticed = re.match(r":(\S+)!\S+ NOTICE (\S+) :(.+)", line)
        moded = re.match(r":(\S+)!\S+ MODE (#\S+) (.+)", line)
        
        if joined:
            joinNick = joined.group(1)
            chan = joined.group(2)
            line = "\t{nick} joined {chan}.".format(nick=joinNick, chan=chan)
        elif kicked:
            kicker = kicked.group(1)
            chan = kicked.group(2)
            kickedNick = kicked.group(3)
            kickMsg = kicked.group(4)
            
            line = "{kicker} kicked {kickee} out of {room}. ({reason})".format(kicker=kicker, kickee=kickedNick,
                                                                               room=chan, reason=kickMsg,)

            if self.botnick.lower() == kickedNick.lower():
                del self.channels[chan.lower()]
        elif parted:
            quitNick = parted.group(1)
            chan = parted.group(2)
            line = "\t{nick} left {chan}.".format(nick=quitNick,
                                                  chan=chan)
        elif quitted:
            quitNick = quitted.group(1)
            line = "\t{nick} quit. ({reason})".format(nick=quitNick,
                                                      reason=quitted.group(2).lstrip(" :"))
        elif moded:
            line = "({chan}){nick} sets mode {mode}".format(chan=moded.group(2),
                                                            nick=moded.group(1),
                                                            mode=moded.group(3))
        elif msged:
            msg = msged.group(3).strip()
            line = "({chan})<{nick}> {msg}".format(chan=msged.group(2),
                                                   nick=msged.group(1),
                                                   msg=msg)
            if "\001ACTION " in msg:
                msg = msg.replace("\001ACTION", "")
                line = "({chan}) * {nick} {acts}".format(chan=msged.group(2),
                                                         nick=msged.group(1),
                                                         acts=msg.strip())
        elif nickChanged:
            oldNick = nickChanged.group(1)
            newNick = nickChanged.group(2)
            line = " * {} is now known as {}.".format(oldNick, newNick)
        elif noticed:
            line = "({chan}) {nick} whispers: {msg}".format(chan=noticed.group(2),
                                                            nick=noticed.group(1),
                                                            msg=noticed.group(3))

        print("[{time}] {line}".format(time=strftime("%H:%M:%S"), line=line))

    def process_data(self, data):
        return

    def raw_send(self, msg, output=None):
        if not output:
            output = msg
            
        counter = 0
        while msg:
            sendMsg = "{m}\r\n".format(msg[:510])
            self.irc.send(sendMsg)
            self.prettify_line(output[:510])

            msg = msg[510:]
            output = msg
            counter += 1
            if counter >= 2:  # Add delay when 2+ lines sent.
                time.sleep(1)
                counter = 0
                
    def say(self, msg, channel, msgType="PRIVMSG", output=None):
        if channel.lower() == self.botnick.lower():
            return
        if not output:
            output = msg

        linesplit = self.variables["Variables"]["delay"]
        delays = re.findall(linesplit, msg)
        for d in delays:
            line = msg.split(d)[0]
            if line.startswith(self.variables["Variables"]["action"]):
                self.act(line, channel)
            else:
                self.raw_send("{} {} :{}\r\n".format(msgType, channel, line), output)
            time.sleep(float(re.search(r"\d+\.?\d*", d).group(0)))
            msg = msg.split(d)[1]
        if msg:
            self.raw_send(msg, output)

    def whois(self, nick, server = ""):
        self.raw_send("WHOIS {s} {nick}\r\n".format(s=server, nick=nick))
        self.searchingWho = True
        while self.searchingWho:
            pass

    def whowas(self, nick, server = ""):
        self.raw_send("WHOWAS {s} {nick}\r\n".format(s=server, nick=nick))
        self.whoSearching = True
        while self.searchingWho:
            pass


class MeatBot(IrcBot):
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


class Server(object):
    def __init__(self, name, host):
        self.name = name  # NETWORK
        self.host = host  # some.server.net
        self.chantypes = ""  # CHANTYPES
        self.prefixes = {}  # PREFIX
        self.maxChannels = 50  # CHANLIMIT
        self.maxChannelLength = 50  # CHANNELLEN
        self.maxKickLength = 80  # KICKLEN
        self.maxNickLength = 9  # NICKLEN
        self.maxTopicLength = 80  # TOPICLEN
        self.caseMapping = ""  # CASEMAPPING


class Channel(object):
    RESET_INTERVAL = 2  # How many seconds to wait before resetting certain values (see reset_values).
    
    def __init__(self, name, isPM=False):
        self.name = name
        self.users = {}  # {"username": User()}
        self.messages = []  # [(raw_message1, time1), (raw_message2, time2)]
        self.isPM = isPM
        self.quiet = False
        self.game = None
        self.song = None

        if not self.isPM:
            ## Determines the limit on greet/gossip messages, resets at an interval:
            self.joinedNum = 0
            self.leftNum = 0
            resetti = threading.Thread(target=self.reset_values)
            resetti.daemon = True
            resetti.start()

    def reset_values(self):
        while True:
            self.joinedNum = 0
            self.leftNum = 0
            time.sleep(self.RESET_INTERVAL)


class User(object):
    def __init__(self, nickname, server):
        self.files = {
            FILE_USERS: lineparser.LineParser(os.path.join(DIR_DATABASE, "users.txt")),
            FILE_SUBJECTS: lineparser.LineParser(os.path.join(DIR_DATABASE, "subjects.txt")),
            }
        for f in self.files:
            f.read_file()
                 
        self.nickname = nickname
        self.idle = False  # True if hasn't talked in any channel for > 5 min?
        self.ignore = False
        self.messages = []  # [IrcMessage(),]
        self.server = server  # Network name: e.g. IRCNet

        try:
            self.userID = self.files[FILE_USERS].get_keys({"user": self.nickname, "server": self.server})[0]
        except IndexError:  # User not in user file.
            self.userID = ALL
    
    @property
    def categories(self):
        """
        Retrieves the categories the user falls in.
        """
        cats = []
        try:
            cats = self.files[FILE_USERS].get_field(self.files[FILE_USERS].get_keys({"user": self.nickname})[0], "category")
            cats = cats.split(",")
        except IndexError:
            pass

        return cats

    def custom_nick(self, includeGeneric=True, includeUsername=True):
        """
        Returns a nickname for the user.
        """
        if includeGeneric:
            filters = {"category": self.categories, "users": ",".join([self.userID, ALL])}
        else:
            filters = {"users": ",".join([self.userID, ALL])}
        nicks = [self.files[FILE_SUBJECTS].get_field(n) for n in self.files[FILE_SUBJECTS].get_keys(filters)]

        if includeUsername:
            nicks.append(self.nickname)
            
        return random.choice(nicks)
    

def main():
    pass

if "__main__" == __name__:
    main()
