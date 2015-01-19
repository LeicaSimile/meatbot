import re
import random
from random import getrandbits
import os.path
import logging
import traceback

import socket
import time
from time import strftime
from datetime import timedelta
import threading
import Queue

import winsound
import win32gui

import urllib2
from bs4 import BeautifulSoup

import ConfigParser
from games import HijackGame

THREAD_MIN = 15


#### ---- IRC Stuff ---- ####
class IrcBot(threading.Thread):
    data = ""
    
    def __init__ (self, host, port, channels, botnick, realname="", auth="", password=""):
        self.host = host
        self.port = port
        self.botnick = botnick

        if not auth:
            self.auth = self.botnick
            
        self.password = password
        self.username = self.botnick
        
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

        remoteIP = socket.gethostbyname(self.host)
        print(remoteIP)

        self.irc.connect((remoteIP, self.port))
        
        self.irc.send("NICK {}\r\n".format(self.botnick))
        self.irc.send("USER {} {} {} :{}\r\n".format(self.username, self.host, self.host, self.realname))

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
                print("The socket timed out, it seems. Trying a connection after 15 seconds.")
                time.sleep(15)
                
                ## Try again.
                self.run()
            finally:
                time.sleep(0.5)

    def act(self, data, channel, action):
        if "#" in channel:
            if self.channels[channel.lower()]["quiet"]:
                return
        if channel.lower() == self.botnick.lower():
            return
            
        ## The bot sends an action ("/me" message).
        sendMsg = "PRIVMSG {chan} :\001ACTION {act}\001\r\n".format(chan = channel, act = action)
        self.irc.send(sendMsg)
        
        prettyMsg = "\n[{time}]({chan}) * {bot} {acts}".format(time=strftime("%H:%M:%S"),
                                                               chan=channel,
                                                               bot=self.botnick,
                                                               acts=action)
        print(prettyMsg)

    def alert(self, message):
        winsound.PlaySound("*", winsound.SND_ALIAS)
        win32gui.MessageBox(0, message, "Keywords! - {time}".format(time=strftime("%H:%M")), 0)
           
        return

    def ask_time(self, server = ""):
        self.irc.send("TIME {s}\r\n".format(s = server))

    def disconnect(self, msg=":("):
        self.irc.send("QUIT :{msg}\r\n".format(msg=msg))
    
    def get_data(self):
        self.init = Settings.Settings().keywords
        self.irc.setblocking(0)  # Non-blocking.
        try:
            data = self.irc.recv(4096)
        except socket.error:
            return

        data = re.sub("\x03\d+", "", data)  # Colour-stripping. Might remove when the bot has a better GUI.
        data = data.splitlines()
        
        for line in data:
            if line.strip():
                self.prettify_data(line)
                self.timeGotData = time.time()
            dataProcess = threading.Thread(target=self.process_data, args=(line,))
            dataProcess.start()

        return

    def init_channel(self, channel):
        self.channels[channel.lower()] = Channel(channel)
            
    def join(self, data, nick, channel, msg=""):
        if channel.lower() != self.botnick.lower() and "#" in channel:
            sendMsg = "JOIN {}\r\n".format(channel)
            if channel.lower() not in self.channels:
                self.init_channel(channel)

            self.irc.send(sendMsg)
            self.prettify_data(sendMsg)
                  
            time.sleep(1)
            if msg:
                self.say(data, channel, msg, "PRIVMSG")
            else:
                if getrandbits(1):
                    self.say(data, channel, self.getMsg(nick, "react", self.init["Headers"]["reaction-jointalk"], channel, True))
                else:
                    self.act(data, channel, self.getMsg(nick, "react", self.init["Headers"]["reaction-joinact"], channel))

        return
                
    def mode(self, param1, param2="", param3=""):
        sendMsg = " ".join(("MODE", param1, param2, param3)).strip()
        sendMsg = "{}\r\n".format(sendMsg)
        self.irc.send(sendMsg)
        print(sendMsg.strip())
        
    def nick_change(self, nick):
        sendMsg = "NICK {nick}\r\n".format(nick=nick)
        self.irc.send(sendMsg)

        ## TODO: Verify nickchange was successful.
        print("You are now {nick}.".format(nick=nick))
        self.botnick = nick

    def part(self, channel, msg=""):
        try:
            del self.channels[channel.lower()]
            sendMsg = "PART {chan} :{msg}\r\n".format(chan=channel, msg=msg)
            self.irc.send(sendMsg)
            print("You left {chan}. ({msg})".format(chan=channel, msg=msg))
        except KeyError:
            pass

    def prettify_data(self, line):
        line = line.strip()
        joined = re.match(r":(\S+)!\S+ JOIN (#\S+)$", line)
        kicked = re.match(r":(\S+)!\S+ KICK (#\S+) (\S+) :(.+)", line)
        parted = re.match(r":(\S+)!\S+ PART (#\S+)$", line)
        quitted = re.match(r":(\S+)!\S+ QUIT(.*)", line)
        msged = re.match(r":(\S+)!\S+ PRIVMSG (\S+) :(.+)", line)
        nick_changed = re.match(r":(\S+)!\S+ NICK :(\S+)", line)
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
        elif nick_changed:
            oldNick = nick_changed.group(1)
            newNick = nick_changed.group(2)
            line = " * {} is now known as {}.".format(oldNick, newNick)
        elif noticed:
            line = "({chan}) {nick} whispers: {msg}".format(chan=noticed.group(2),
                                                            nick=noticed.group(1),
                                                            msg=noticed.group(3))

        print("[{time}] {line}".format(time=strftime("%H:%M:%S"), line=line))

    def process_data(self, data):
        try:
            nick = data.split("!")[0].translate(None, ":")
        except AttributeError:
            pass

        ## Respond to server pings:
        if "PING" in data.split(" ")[0]:
            pongMsg = "PONG {}\r\n".format(data.split("PING ")[1])
            self.irc.send(pongMsg)
            print("[{time}] {pong}".format(time=strftime("%H:%M:%S"), pong=pongMsg))

        ## Join channels after the message of the day is out.
        if re.match(r"(?i):\S+ \d+ {bot}.* :End of /MOTD".format(bot=self.botnick.lower()), data.lower()):
            sendMsg = "PRIVMSG NICKSERV :IDENTIFY {own} {pword}\r\n".format(own=self.auth, pword=self.password)
            self.irc.send(sendMsg)
            print("(NickServ)<You> I am totally {own}. Seriously.".format(own=self.auth))

            sendMsg = "MODE {bot} +R\r\n".format(bot=self.botnick)
            self.irc.send(sendMsg)
            print(sendMsg.strip())
            for chan in self.channels:
                joinThread = threading.Thread(target=self.join, args=(data, nick, chan))
                joinThread.start()

        ## Ghost any past copies of the bot already inside.
        nickUsed = re.match(r":\S+ \d+ \S+ (\w+) :Nickname is already in use", data, re.I)
        if nickUsed:
            self.nick_change("{}_".format(nickUsed.group(1)))
            self.say("GHOST {} {}".format(nickUsed.group(1), self.password))
            
        if re.match(r":\S+ NOTICE \S+ :.?\S+.? (is not online|has been ghosted)", data.lower(), re.I):
            self.nick_change(self.botnick)

        ## Get channel and user prefixes that represent modes (opped, voiced, moderated, etc.).
        gotChanPrefixes = re.match(r"(?i):.+{bot} .+ PREFIX=\(\w+\)(\S+) .+:are supported by this server".format(bot=self.botnick.lower()),
                                   data.lower())
        if gotChanPrefixes:
            self.chanPrefixes = gotChanPrefixes.group(1)
        else:
            self.chanPrefixes = "@+"

        showedNames = re.match(r"(?i):\S+ \d+ {}.? \S (#\S+) :".format(self.botnick), data)
        if showedNames:
            channel = showedNames.group(1)
            users = data.split(showedNames.group(0))[1].translate(None, self.chanPrefixes)
            self.channels[channel.lower()]["users"] = users.split(" ")
            print(self.channels[channel.lower()]["users"])
        
        whoIdMatch = re.match(r"(?i):\S+ \d+ {bot}.? (\S+) (\S+) :(wa|i)s logged in as".format(bot = self.botnick), data)
        whoIdleMatch = re.match(r"(?i):\S+ \d+ {bot}.? \S+ (\d+ \d+) :second".format(bot = self.botnick), data)
        whoDateMatch = re.match(r"(?i):\S+ \d+ {bot}.? \S+ (\S+) :(\S+ \S+ \d+ \d+:\d+:\d+ \d+)".format(bot = self.botnick), data)
        whoServerMatch = re.match(r"(?i):\S+ \d+ {bot}.? \S+ (\S+\.\S+((\.\S+)+)?) :".format(bot = self.botnick), data)
        endWhoMatch = re.match(r"(?i):\S+ \d+ {bot}.? \S+ :End of (/WHOIS list|WHOWAS)".format(bot = self.botnick.lower()), data.lower())

        if whoIdMatch:
            self.whoNick = whoIdMatch.group(1)
            self.whoIdentity = whoIdMatch.group(2)
        if whoIdleMatch:
            self.whoIdle = whoIdleMatch.group(1)
        if whoDateMatch:
            self.whoServer = whoDateMatch.group(1)
            self.whoLoginDate = whoDateMatch.group(2)
        if whoServerMatch:
            self.whoServer = whoServerMatch.group(1)
        if endWhoMatch:
            self.searchingWho = False
            
        inviteMatch = re.match(r"(?i):\S+ INVITE {}.? :(#\S+)".format(self.botnick.lower()), data.lower())
        if inviteMatch:
            self.join(data, nick, inviteMatch.group(1))

        return
                
    def say(self, msg, channel, msgType="PRIVMSG"):
        ## channel = channel OR user
        if channel.lower() == self.botnick.lower():
            return

        if isinstance(msg, list):
            ## Sample list = [(line1, delay1), (line2, delay2)]
            for line in msg:
                time.sleep(line[1])
                self.irc.send("{} {} :{msg}\r\n".format(msgType.upper(), channel, line[0]))
        else:
            counter = 0
            while msg:
                sendMsg = "{msgType} {chan} :{msg}\r\n".format(msgType=msgType.upper(), chan=channel, msg=msg[:510])
                self.irc.send(sendMsg)
                
                prettyMsg = "[{time}]({chan})<{bot}> {msg}".format(time=strftime("%H:%M:%S"),
                                                                   chan=channel,
                                                                   bot=self.botnick,
                                                                   msg=msg[:510])    
                print(prettyMsg)
                msg = msg[510:]
                counter += 1

                if counter >= 2:
                    time.sleep(1)
                    counter = 0


    def whois(self, nick, server = ""):
        self.irc.send("WHOIS {s} {nick}\r\n".format(s=server, nick=nick))
        self.searchingWho = True
        while self.searchingWho:
            pass

    def whowas(self, nick, server = ""):
        self.irc.send("WHOWAS {s} {nick}\r\n".format(s=server, nick=nick))
        self.whoSearching = True
        while self.searchingWho:
            pass


class MeatBot(IrcBot):
    def __init__(self, configFile="config.ini"):
        pass


class Channel(object):
    def __init__(self, name):
        self.name = name
        self.users = []


class User(object):
    def __init__(self, nickname):
        self.nickname = nickname
        self.idle = False  # True if hasn't talked in any channel for > 5 min?
        self.isBlocked = False

    @property
    def privileges(self):
        return ":)"
    

def main():
    print(True)

if "__main__" == __name__:
    main()
