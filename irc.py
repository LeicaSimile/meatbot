# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
import logging
import logging.config
import random
import socket
import time
import threading

import lineparser

logging.config.fileConfig("logging.ini")
logger = logging.getLogger("irc")

try:
    unicode  # Python 2
except NameError:
    unicode = str  # Python 3


#### ---- IRC Stuff ---- ####
class IrcMessage(object):
    """
    For parsing IRC messages.
    """
    def __init__(self, message, timestamp=None):
        self.rawMsg = message  # Full message as was sent.
        self.command = ""
        self.parameters = ""
        self.message = ""  # Privmsgs, notices, quit messages, etc.
        self.sender = ""
        
        if timestamp is None:
            self.timestamp = time.time()
        else:
            self.timestamp = timestamp
            
        self._basic_parse()

    def __str__(self):
        return self.rawMsg

    def _basic_parse(self):
        """
        Identify basic properties of message (sender and command).
        """
        message = self.rawMsg.strip()
        matchUserMsg = re.match(r":(\S+)!\S+ (\w+) ", message)
        matchServerMsg = re.match(r":(\S+) (\S+) ", message)
        matched = " "

        if matchUserMsg:
            self.sender = matchUserMsg.group(1)
            self.command = matchUserMsg.group(2)
            matched = matchUserMsg.group(0)
        else:  # Server message.
            if message.startswith("PING "):
                self.command = "PING"
                matched = "PING "
            elif matchServerMsg:
                self.sender = matchServerMsg.group(1)
                self.command = matchServerMsg.group(2)
                matched = matchServerMsg.group(0)
        try:
            self.parameters = message.split(matched, 1)[1]
        except IndexError:
            self.parameters = ""
        else:
            self.message = self.parameters.split(":", 1)
            try:
                self.message = self.message[1]
            except IndexError:
                self.message = ""

    @property
    def channel(self):
        chan = ""
        params = self.parameters.split(" ")
        positions = {0: ["JOIN", "KICK", "NOTICE", "PART", "PRIVMSG", "TOPIC"],
                     1: ["INVITE"],}

        for pos in positions:
            if self.command in positions[pos]:
                try:
                    chan = params[pos]
                except IndexError:
                    logger.warning("IrcMessage only has {} parameters (tried to select index {})".format(len(params), pos))
                    chan = ""

        return chan.lstrip(":")

    @property
    def cleanMsg(self):
        msg = self.rawMsg

        if "INVITE" == self.command:
            params = self.parameters.split(" ")
            guest = params[0]
            
            msg = "{n} has invited {who} to {chan}.".format(n=self.sender, who=guest, chan=self.channel)
            
        elif "JOIN" == self.command:
            msg = "\t{n} joined {chan}.".format(n=self.sender, chan=self.channel)
            
        elif "KICK" == self.command:
            params = self.parameters.split(" ")
            kicked = params[1]
            
            msg = "{n} kicked {k} out of {chan}. ({r})".format(n=self.sender, k=kicked, chan=self.channel, r=self.message)
            
        elif "MODE" == self.command:
            params = self.parameters.split(" ")
            mode = params[1]
            what = params[0]
            
            msg = "{n} sets mode {m} on {w}.".format(n=self.sender, m=mode, w=what)
            
        elif "NICK" == self.command:
            msg = "{old} is now known as {new}.".format(old=self.sender, new=self.message)
            
        elif "NOTICE" == self.command:
            msg = "({chan}) - {n} whispers: {m}".format(chan=self.channel, n=self.sender, m=self.message)
            
        elif "PART" == self.command:
            msg = "\t{n} left {chan}. ({r})".format(n=self.sender, chan=self.channel, r=self.message)
            
        elif "PRIVMSG" == self.command:
            if self.message.startswith("\001ACTION"):
                msg = self.message.replace("\001ACTION", "")
                msg = msg.replace("\001", "").lstrip()
                msg = "({chan}) * {n} {m}".format(chan=self.channel, n=self.sender, m=msg)
            else:
                msg = "({chan}) <{n}> {m}".format(chan=self.channel, n=self.sender, m=self.message)
            
        elif "QUIT" == self.command:
            msg = "{n} quit. ({r})".format(n=self.sender, r=self.message)
            
        elif "TOPIC" == self.command:
            msg = "({chan}) {n} has set the topic to: {t}".format(chan=self.channel, n=self.sender, t=self.message)

        elif self.command.isdigit():  # Server numeric message
            msg = "({s}) {m}".format(s=self.sender, m=self.message)

        return msg
        

class IrcBot(threading.Thread):
    def __init__ (self, server, host, port, channels, botnick, realname="", auth="", password=""):
        self.host = host
        self.port = port
        self.botnick = botnick
        self.channels = {}

        if not auth:
            self.auth = self.botnick
        else:
            self.auth = auth
            
        self.password = password
        self.username = self.botnick
        self.realname = realname
        self.owner = ""

        self.server = Server(server, host)
        self.server.users[self.botnick.lower()] = User(self.botnick, self.server)
        
        self.init_channel(self.botnick)
        for chan in channels:
            self.init_channel(chan)
        
        self.dataThreads = []
        self.timeGotData = time.time()
        
        threading.Thread.__init__(self)

    def run(self):
        chans = [chan for chan in self.channels]
        self.__init__(server=self.server,
                      host=self.host,
                      port=self.port,
                      channels=chans,
                      botnick=self.botnick,
                      realname=self.realname,
                      auth=self.auth,
                      password=self.password)
        
        ## Try to connect to server.
        try:
            self.irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.error:
            logger.exception("Failed to create socket.")
            return

        self.remoteIP = socket.gethostbyname(self.host)
        logger.info(self.remoteIP)

        self.irc.connect((self.remoteIP, self.port))
        
        self.nick_change(self.botnick)

        msg = "USER {} {} * :{}".format(self.username, self.host, self.realname)
        self.raw_send("{}\r\n".format(msg))
        logger.info(msg)

        while True:
            try:
                self.get_data()
                
                if 200 < time.time() - self.timeGotData:
                    ## 200+ seconds passed since last message. Try reconnecting.
                    self.run()
            except IOError:
                logger.exception("IO Error encountered.")
            except socket.timeout:
                logger.warning("The socket timed out. Trying a connection after 15 seconds.")
                time.sleep(15)
                
                ## Try again.
                self.run()
            finally:
                time.sleep(0.5)

    def act(self, action, channel, logOutput=None):
        channel = channel.lower()
        if "#" in channel:
            if self.channels[channel].quiet:
                return
        if channel == self.botnick.lower() or self.channels[channel].quiet:
            return
            
        ## The bot sends an action ("/me" message).
        sendMsg = "PRIVMSG {chan} :\001ACTION {a}\001\r\n".format(chan=channel, a=action)
        self.raw_send(sendMsg, logOutput)
        
    def alert(self, message):
        pass

    def ask_time(self, server=""):
        msg = "TIME {}".format(server)
        self.raw_send("{}\r\n".format(msg))
        logger.info(msg)

    def colour_strip(self, text):
        try:
            return re.sub(r"\x03\d+", "", text)
        except TypeError:
            return re.sub(r"\x03\d+", "", unicode(text, "utf-8"))

    def disconnect(self, msg=""):
        self.raw_send("QUIT :{m}\r\n".format(m=msg))

    def get_auth(self, user):
        self.whois(user)
        
    def get_data(self):
        self.irc.setblocking(0)  # Non-blocking.
        try:
            data = self.irc.recv(4096)
        except socket.error:
            return

        data = unicode(data, "utf-8")
        data = self.colour_strip(data)  # Might disable when the bot has a better GUI.
        data = data.splitlines()
        
        for line in data:
            if line.strip():
                self.timeGotData = time.time()
            dataProcess = threading.Thread(target=self.process_line, args=(line,))
            dataProcess.start()

        return

    def identify(self, service="NickServ", command="IDENTIFY"):
        self.say(" ".join([command, self.auth, self.password]), service,
                 logOutput="({s}) {c} {a} {p}".format(s=service, c=command,
                                                      a=self.auth, p="*".rjust(len(self.password), "*"))
                 )

    def init_channel(self, channel, isPM=False):
        self.channels[channel.lower()] = Channel(channel, isPM)
        
    def join(self, channel):
        if channel.lower() == self.botnick.lower():
            return

        if channel.lower().startswith(tuple(self.server.chantypes)):
            sendMsg = "JOIN {}\r\n".format(channel)
            self.raw_send(sendMsg, "Attempting to join {}".format(channel))
            
        return
                
    def mode(self, param1, param2="", param3=""):
        parameters = " ".join((param1, param2, param3)).strip()
        sendMsg = "MODE {}\r\n".format(sendMsg)
        self.raw_send(sendMsg)
        
    def nick_change(self, nick):
        sendMsg = "NICK {nick}\r\n".format(nick=nick)
        self.raw_send(sendMsg)

    def part(self, channel, msg=""):
        try:
            del self.channels[channel.lower()]
            sendMsg = "PART {chan} :{m}\r\n".format(chan=channel, m=msg)
            self.raw_send(sendMsg)
        except KeyError:
            logger.warning("{} was not in {}.".format(self.botnick, channel))

    def process_line(self, line):
        """
        Args:
            line(unicode): line to process
        """
        handlers = {
            "INVITE": self.on_invite,
            "JOIN": self.on_join,
            "KICK": self.on_kick,
            "MODE": self.on_mode,
            "NICK": self.on_nickchange,
            "NOTICE": self.on_notice,
            "PART": self.on_part,
            "PASS": self.on_pass,
            "PING": self.on_ping,
            "PRIVMSG": self.on_privmsg,
            "QUIT": self.on_quit,
            "TOPIC": self.on_topic,
            "001": self.on_rpl_welcome,  # "RPL_WELCOME"
            "002": self.on_rpl_yourhost,  # "RPL_YOURHOST"
            "003": self.on_rpl_created,  # "RPL_CREATED"
            "004": self.on_rpl_myinfo,  # "RPL_MYINFO"
            "005": self.on_rpl_isupport,  # "RPL_ISUPPORT"
            "008": self.on_rpl_snomask,  # "RPL_SNOMASK"
            "009": self.on_rpl_statmemtot,  # "RPL_STATMEMTOT"
            "010": self.on_rpl_bounce,  # "RPL_BOUNCE"
            "200": self.on_rpl_tracelink,  # "RPL_TRACELINK"
            "201": self.on_rpl_traceconnecting,  # "RPL_TRACECONNECTING"
            "202": self.on_rpl_tracehandshake,  # "RPL_TRACEHANDSHAKE"
            "203": self.on_rpl_traceunknown,  # "RPL_TRACEUNKNOWN"
            "204": self.on_rpl_traceoperator,  # "RPL_TRACEOPERATOR"
            "205": self.on_rpl_traceuser,  # "RPL_TRACEUSER"
            "206": self.on_rpl_traceserver,  # "RPL_TRACESERVER"
            "208": self.on_rpl_tracenewtype,  # "RPL_TRACENEWTYPE"
            "209": self.on_rpl_traceclass,  # "RPL_TRACECLASS"
            "211": self.on_rpl_statslinkinfo,  # "RPL_STATSLINKINFO"
            "212": self.on_rpl_statscommands,  # "RPL_STATSCOMMANDS"
            "213": self.on_rpl_statscline,  # "RPL_STATSCLINE"
            "214": self.on_rpl_statsnline,  # "RPL_STATSNLINE"
            "215": self.on_rpl_statsiline,  # "RPL_STATSILINE"
            "216": self.on_rpl_statskline,  # RPL_STATSKLINE
            "217": self.on_rpl_statsqline,  # RPL_STATSQLINE
            "218": self.on_rpl_statsyline,  # RPL_STATSYLINE
            "219": self.on_rpl_endofstats,  # RPL_ENDOFSTATS
            "231": self.on_rpl_serviceinfo,  # RPL_SERVICEINFO
            "232": self.on_rpl_endofservices,  # RPL_ENDOFSERVICES
            "233": self.on_rpl_service,  # RPL_SERVICE
            "234": self.on_rpl_servlist,  # RPL_SERVLIST
            "235": self.on_rpl_servlistend,  # RPL_SERVLISTEND
            "241": self.on_rpl_statslline,  # RPL_STATSLLINE
            "242": self.on_rpl_statsuptime,  # RPL_STATSUPTIME
            "243": self.on_rpl_statsoline,  # RPL_STATSOLINE
            "244": self.on_rpl_statshline,  # RPL_STATSHLINE
            "221": self.on_rpl_umodeis,  # RPL_UMODEIS
            "251": self.on_rpl_luserclient,  # RPL_LUSERCLIENT
            "252": self.on_rpl_luserop,  # RPL_LUSEROP
            "253": self.on_rpl_luserunknown,  # RPL_LUSERUNKNOWN
            "254": self.on_rpl_luserchannels,  # RPL_LUSERCHANNELS
            "255": self.on_rpl_luserme,  # RPL_LUSERME
            "256": self.on_rpl_adminme,  # RPL_ADMINME
            "257": self.on_rpl_adminloc1,  # RPL_ADMINLOC1
            "258": self.on_rpl_adminloc2,  # RPL_ADMINLOC2
            "259": self.on_rpl_adminemail,  # RPL_ADMINEMAIL
            "261": self.on_rpl_tracelog,  # RPL_TRACELOG
            "300": self.on_rpl_none,  # RPL_NONE
            "301": self.on_rpl_away,  # RPL_AWAY
            "302": self.on_rpl_userhost,  # RPL_USERHOST
            "303": self.on_rpl_ison,  # RPL_ISON
            "305": self.on_rpl_unaway,  # RPL_UNAWAY
            "306": self.on_rpl_nowaway,  # RPL_NOWAWAY
            "311": self.on_rpl_whoisuser,  # RPL_WHOISUSER
            "312": self.on_rpl_whoisserver,  # RPL_WHOISSERVER
            "313": self.on_rpl_whoisoperator,  # RPL_WHOISOPERATOR
            "314": self.on_rpl_whowasuser,  # RPL_WHOWASUSER
            "315": self.on_rpl_endofwho,  # RPL_ENDOFWHO
            "316": self.on_rpl_whoischanop,  # RPL_WHOISCHANOP
            "317": self.on_rpl_whoisidle,  # RPL_WHOISIDLE
            "318": self.on_rpl_endofwhois,  # RPL_ENDOFWHOIS
            "319": self.on_rpl_whoischannels,  # RPL_WHOISCHANNELS
            "321": self.on_rpl_liststart,  # RPL_LISTSTART
            "322": self.on_rpl_list,  # RPL_LIST
            "323": self.on_rpl_listend,  # RPL_LISTEND
            "324": self.on_rpl_channelmodeis,  # RPL_CHANNELMODEIS
            "331": self.on_rpl_notopic,  # RPL_NOTOPIC
            "332": self.on_rpl_topic,  # RPL_TOPIC
            "341": self.on_rpl_inviting,  # RPL_INVITING
            "342": self.on_rpl_summoning,  # RPL_SUMMONING
            "351": self.on_rpl_version,  # RPL_VERSION
            "352": self.on_rpl_whoreply,  # RPL_WHOREPLY
            "353": self.on_rpl_namreply,  # RPL_NAMREPLY
            "361": self.on_rpl_killdone,  # RPL_KILLDONE
            "362": self.on_rpl_closing,  # RPL_CLOSING
            "363": self.on_rpl_closeend,  # RPL_CLOSEEND
            "366": self.on_rpl_endofnames,  # RPL_ENDOFNAMES
            "364": self.on_rpl_links,  # RPL_LINKS
            "365": self.on_rpl_endoflinks,  # RPL_ENDOFLINKS
            "367": self.on_rpl_banlist,  # RPL_BANLIST
            "368": self.on_rpl_endofbanlist,  # RPL_ENDOFBANLIST
            "369": self.on_rpl_endofwhowas,  # RPL_ENDOFWHOWAS
            "371": self.on_rpl_info,  # RPL_INFO
            "372": self.on_rpl_motd,  # RPL_MOTD
            "373": self.on_rpl_infostart,  # RPL_INFOSTART
            "374": self.on_rpl_endofinfo,  # RPL_ENDOFINFO
            "375": self.on_rpl_motdstart,  # RPL_MOTDSTART
            "376": self.on_rpl_endofmotd,  # RPL_ENDOFMOTD
            "381": self.on_rpl_youreoper,  # RPL_YOUREOPER
            "382": self.on_rpl_rehashing,  # RPL_REHASHING
            "384": self.on_rpl_myportis,  # RPL_MYPORTIS
            "391": self.on_rpl_time,  # RPL_TIME
            "392": self.on_rpl_usersstart,  # RPL_USERSSTART
            "393": self.on_rpl_users,  # RPL_USERS
            "394": self.on_rpl_endofusers,  # RPL_ENDOFUSERS
            "395": self.on_rpl_nousers,  # RPL_NOUSERS
            "401": self.on_err_nosuchnick,  # ERR_NOSUCHNICK
            "402": self.on_err_nosuchserver,  # ERR_NOSUCHSERVER
            "403": self.on_err_nosuchchannel,  # ERR_NOSUCHCHANNEL
            "404": self.on_err_cannotsendtochan,  # ERR_CANNOTSENDTOCHAN
            "405": self.on_err_toomanychannels,  # ERR_TOOMANYCHANNELS
            "406": self.on_err_wasnosuchnick,  # ERR_WASNOSUCHNICK
            "407": self.on_err_toomanytargets,  # ERR_TOOMANYTARGETS
            "409": self.on_err_noorigin,  # ERR_NOORIGIN
            "411": self.on_err_norecipient,  # ERR_NORECIPIENT
            "412": self.on_err_notexttosend,  # ERR_NOTEXTTOSEND
            "413": self.on_err_notoplevel,  # ERR_NOTOPLEVEL
            "414": self.on_err_wildtoplevel,  # ERR_WILDTOPLEVEL
            "421": self.on_err_unknowncommand,  # ERR_UNKNOWNCOMMAND
            "422": self.on_err_nomotd,  # ERR_NOMOTD
            "423": self.on_err_noadmininfo,  # ERR_NOADMININFO
            "424": self.on_err_fileerror,  # ERR_FILEERROR
            "431": self.on_err_nonicknamegiven,  # ERR_NONICKNAMEGIVEN
            "432": self.on_err_erroneusnickname,  # ERR_ERRONEUSNICKNAME
            "433": self.on_err_nicknameinuse,  # ERR_NICKNAMEINUSE
            "436": self.on_err_nickcollision,  # ERR_NICKCOLLISION
            "441": self.on_err_usernotinchannel,  # ERR_USERNOTINCHANNEL
            "442": self.on_err_notonchannel,  # ERR_NOTONCHANNEL
            "443": self.on_err_useronchannel,  # ERR_USERONCHANNEL
            "444": self.on_err_nologin,  # ERR_NOLOGIN
            "445": self.on_err_summondisabled,  # ERR_SUMMONDISABLED
            "446": self.on_err_usersdisabled,  # ERR_USERSDISABLED
            "451": self.on_err_notregistered,  # ERR_NOTREGISTERED
            "461": self.on_err_needmoreparams,  # ERR_NEEDMOREPARAMS
            "462": self.on_err_alreadyregistred,  # ERR_ALREADYREGISTRED
            "463": self.on_err_nopermforhost,  # ERR_NOPERMFORHOST
            "464": self.on_err_passwdmismatch,  # ERR_PASSWDMISMATCH
            "465": self.on_err_yourebannedcreep,  # ERR_YOUREBANNEDCREEP
            "466": self.on_err_youwillbebanned,  # ERR_YOUWILLBEBANNED
            "467": self.on_err_keyset,  # ERR_KEYSET
            "471": self.on_err_channelisfull,  # ERR_CHANNELISFULL
            "472": self.on_err_unknownmode,  # ERR_UNKNOWNMODE
            "473": self.on_err_inviteonlychan,  # ERR_INVITEONLYCHAN
            "474": self.on_err_bannedfromchan,  # ERR_BANNEDFROMCHAN
            "475": self.on_err_badchannelkey,  # ERR_BADCHANNELKEY
            "476": self.on_err_badchanmask,  # ERR_BADCHANMASK
            "481": self.on_err_noprivileges,  # ERR_NOPRIVILEGES
            "482": self.on_err_chanoprivsneeded,  # ERR_CHANOPRIVSNEEDED
            "483": self.on_err_cantkillserver,  # ERR_CANTKILLSERVER
            "491": self.on_err_nooperhost,  # ERR_NOOPERHOST
            "492": self.on_err_noservicehost,  # ERR_NOSERVICEHOST
            "501": self.on_err_umodeunknownflag,  # ERR_UMODEUNKNOWNFLAG
            "502": self.on_err_usersdontmatch,  # ERR_USERSDONTMATCH
            }
        
        line = IrcMessage(line, time.time())
        if line.command in handlers:
            handlers[line.command](line)

        logger.info(line.cleanMsg)
        logger.debug(line.rawMsg)

    def raw_send(self, msg, logOutput=None):
        """
        Sends a message exactly as specified to the server.
        
        Args:
            msg(unicode): Message to send to server.
        """
        counter = 0
        while msg:
            sendMsg = "{}\r\n".format(msg[:510])
            b_sendMsg = sendMsg.encode("utf-8")
            
            self.irc.send(b_sendMsg)

            if logOutput is None:
                s = IrcMessage(":{}!{} {}".format(self.botnick, self.host, sendMsg))
                logger.info(s.cleanMsg)

            msg = msg[510:]
            counter += 1
            if counter >= 2:  # Add delay when 2+ lines sent.
                time.sleep(1)
                counter = 0

        if logOutput is not None:
            logger.info(logOutput)
                
    def say(self, msg, channel, msgType="PRIVMSG", logOutput=None):
        """
        Sends a message to a channel (or user).

        Args:
            msg(unicode): Message to send.
            channel(unicode): Channel to send message to.
            msgType(unicode, optional): PRIVMSG (default) or NOTICE (whisper).
            logOutput(unicode, optional): What to put in the log (level INFO).
        """
        channel = channel.lower()
        if channel not in self.channels:
            self.init_channel(channel)
            
        if channel == self.botnick.lower() or self.channels[channel].quiet:
            return

        linesplit = lineparser.get_setting("Variables", "delay")
        delays = re.findall(linesplit, msg)
        
        if delays:
            for d in delays:
                line = msg.split(d)[0]
                if line.startswith(lineparser.get_setting("Variables", "action")):
                    self.act(line, channel, logOutput)
                else:
                    self.raw_send("{} {} :{}".format(msgType, channel, line), logOutput)
                time.sleep(float(re.search(r"\d+\.?\d*", d).group(0)))
                msg = msg.split(d)[1]
        elif msg:
            if msg.startswith(lineparser.get_setting("Variables", "action")):
                self.act(msg, channel, logOutput)
            else:
                self.raw_send("{} {} :{}".format(msgType, channel, msg), logOutput)

    def whois(self, nick, server=""):
        msg = "WHOIS {s} {n}".format(s=server, n=nick)
        self.raw_send("{}\r\n".format(msg))
        logger.info(msg)

    def whowas(self, nick, server=""):
        msg = "WHOWAS {s} {n}".format(s=server, n=nick)
        self.raw_send("{}\r\n".format(msg))
        logger.info(msg)
        

    ## -- Methods launched in response to an event: -- ##
    def on_invite(self, msg):
        pass

    def on_join(self, msg):
        """
        When a user joins a channel. (e.g. :nickname!hoststuff JOIN #channel)
        Add user to channel list, and add channel to user's list.

        Args:
            msg(IrcMessage): The join message.
        """
        channel = msg.parameters.split(" ")[0].lower()
        nicklower = msg.sender.lower()
        
        if channel not in self.channels:
            self.init_channel(msg.parameters.split(" ")[0])
            
        if nicklower == self.botnick.lower():  # No need to react to self joining.
            return
        
        if nicklower not in self.server.users:
            self.server.users[nicklower] = User(msg.sender, self.server)
            
        self.channels[channel].users.append(nicklower)
        self.server.users[nicklower].channels.append(channel)

    def on_kick(self, msg):
        """
        When a user kicks another user out from a channel. (e.g. :nickname1!hoststuff KICK #channel nickname2 :This is why we can't have nice things.)
        Remove user from channel list, and remove channel from kicked user's list.

        Args:
            msg(IrcMessage): The kick message.
        """
        msg.parameters = msg.parameters.split(" ", 2)

        kicker = msg.sender.lower()
        channel = msg.parameters[0].lower()
        kicked = msg.parameters[1].lower()
        kickMsg = msg.parameters[2].lstrip(":")

        self.channels[channel].users.remove(kicked)
        
        try:
            self.server.users[kicked].channels.remove(channel)
        except ValueError:
            logging.warning("{} was not in {}.".format(kicked, msg.parameters[0]))

    def on_mode(self, msg):
        pass

    def on_nickchange(self, msg):
        """
        When a user changes their nickname. (e.g. :nickname!hoststuff NICK :newnick)
        Update user's nickname.

        Args:
            msg(IrcMessage): The nick change message.
        """
        oldnick = msg.sender.lower()
        newnick = msg.parameters.split(":")[1].lower()

        try:
            self.server.users[newnick] = self.server.users[oldnick]
        except KeyError:
            logger.error("{} was not in {} userlist.".format(oldnick, self.server))
        else:
            self.server.users[newnick].nickname = msg.parameters.split(":")[1]

            for chan in self.server.users[newnick].channels:
                self.channels[chan].users.append(newnick)
                self.channels[chan].users.remove(oldnick)

            

            del self.server.users[oldnick]

            logger.debug("Updated userlist with {}: {}".format(msg.parameters.split(":")[1], self.server.users))
    
    def on_notice(self, msg):
        pass

    def on_part(self, msg):
        """
        When a user leaves a channel. (e.g. :nickname!hoststuff PART #channel :Because reasons.)
        Remove user from channel list, and remove channel from user's list.

        Args:
            msg(IrcMessage): The part message.
        """
        leaver = msg.sender.lower()
        channel = msg.parameters.split(" ")[0].lower()
        try:
            reason = msg.parameters.split(" :")[1]
        except IndexError:
            reason = ""

        self.channels[channel].users.remove(leaver)

        try:
            self.server.users[leaver].channels.remove(channel)
        except ValueError:
            logging.warning("{} was not in {}.".format(leaver, channel))

    def on_pass(self, msg):
        pass
    
    def on_ping(self, msg):
        self.raw_send("PONG {}".format(msg.parameters))
    
    def on_privmsg(self, msg):
        pass

    def on_quit(self, msg):
        """
        When a user quits. (e.g. :nickname!hoststuff QUIT :See you in two weeks.)
        Remove user from userlist of the server and all channels they were in.
        """
        leavernick = msg.sender.lower()

        try:
            leaver = self.server.users[leavernick]
        except KeyError:
            logger.warning("{} was not in {} userlist.".format(leavernick, self.server))
        else:
            for chan in leaver.channels:
                self.channels[chan].users.remove(leavernick)
                
            del self.server.users[leavernick]

    def on_topic(self, msg):
        pass

    ## Server numeric event handlers:
    def on_rpl_welcome(self, msg):
        """
        Welcome message from the server. Cue to take note of the specific host.

        Args:
            msg(IrcMessage): The message from the server.
        """
        try:
            self.server.host = re.search(r":(\S+) 001", msg.rawMsg).group(1)
        except AttributeError:
            logger.warning("Server host not found in welcome message.")
        
    def on_rpl_yourhost(self, msg):
        pass

    def on_rpl_created(self, msg):
        pass

    def on_rpl_myinfo(self, msg):
        pass

    def on_rpl_isupport(self, msg):
        """
        The message from the server indicating things such as chantypes, max nick length, and max topic length.
        See: http://www.irc.org/tech_docs/005.html

        Args:
            msg(IrcMessage): The message from the server.
        """
        casemappingMatch = re.search(r"CASEMAPPING=(\S+)", msg.rawMsg)
        chantypesMatch = re.search(r"CHANTYPES=(\S+)", msg.rawMsg)
        chanlimitMatch = re.search(r"CHANLIMIT=\S+(\d+)", msg.rawMsg)
        channellenMatch = re.search(r"CHANNELLEN=(\d+)", msg.rawMsg)
        kicklenMatch = re.search(r"KICKLEN=(\d+)", msg.rawMsg)
        nicklenMatch = re.search(r"NICKLEN=(\d+)", msg.rawMsg)
        prefixMatch = re.search(r"PREFIX=\((\w+)\)(\S+)", msg.rawMsg)
        topiclenMatch = re.search(r"TOPICLEN=(\d+)", msg.rawMsg)

        if casemappingMatch:
            self.server.caseMapping = casemappingMatch.group(1)
        if chantypesMatch:
            self.server.chantypes = chantypesMatch.group(1)
        if chanlimitMatch:
            self.server.maxChannels = int(chanlimitMatch.group(1))
        if channellenMatch:
            self.server.maxChannelLength = int(channellenMatch.group(1))
        if kicklenMatch:
            self.server.maxKickLength = int(kicklenMatch.group(1))
        if nicklenMatch:
            self.server.maxNickLength = int(nicklenMatch.group(1))
        if topiclenMatch:
            self.server.maxTopicLength = int(topiclenMatch.group(1))
        if prefixMatch:
            index = 0
            for char in prefixMatch.group(1):
                self.server.prefixes[char] = prefixMatch.group(2)[index]
                index += 1
        
    def on_rpl_snomask(self, msg):
        pass

    def on_rpl_statmemtot(self, msg):
        pass

    def on_rpl_bounce(self, msg):
        pass

    def on_rpl_tracelink(self, msg):
        pass

    def on_rpl_traceconnecting(self, msg):
        pass

    def on_rpl_tracehandshake(self, msg):
        pass

    def on_rpl_traceunknown(self, msg):
        pass

    def on_rpl_traceoperator(self, msg):
        pass

    def on_rpl_traceuser(self, msg):
        pass

    def on_rpl_traceserver(self, msg):
        pass

    def on_rpl_tracenewtype(self, msg):
        pass

    def on_rpl_traceclass(self, msg):
        pass

    def on_rpl_statslinkinfo(self, msg):
        pass

    def on_rpl_statscommands(self, msg):
        pass

    def on_rpl_statscline(self, msg):
        pass

    def on_rpl_statsnline(self, msg):
        pass

    def on_rpl_statsiline(self, msg):
        pass

    def on_rpl_statskline(self, msg):
        pass

    def on_rpl_statsqline(self, msg):
        pass

    def on_rpl_statsyline(self, msg):
        pass

    def on_rpl_endofstats(self, msg):
        pass

    def on_rpl_serviceinfo(self, msg):
        pass

    def on_rpl_endofservices(self, msg):
        pass

    def on_rpl_service(self, msg):
        pass

    def on_rpl_servlist(self, msg):
        pass

    def on_rpl_servlistend(self, msg):
        pass

    def on_rpl_statslline(self, msg):
        pass

    def on_rpl_statsuptime(self, msg):
        pass

    def on_rpl_statsoline(self, msg):
        pass

    def on_rpl_statshline(self, msg):
        pass

    def on_rpl_umodeis(self, msg):
        pass

    def on_rpl_luserclient(self, msg):
        pass

    def on_rpl_luserop(self, msg):
        pass

    def on_rpl_luserunknown(self, msg):
        pass

    def on_rpl_luserchannels(self, msg):
        pass

    def on_rpl_luserme(self, msg):
        pass

    def on_rpl_adminme(self, msg):
        pass

    def on_rpl_adminloc1(self, msg):
        pass

    def on_rpl_adminloc2(self, msg):
        pass

    def on_rpl_adminemail(self, msg):
        pass

    def on_rpl_tracelog(self, msg):
        pass

    def on_rpl_none(self, msg):
        pass

    def on_rpl_away(self, msg):
        pass

    def on_rpl_userhost(self, msg):
        pass

    def on_rpl_ison(self, msg):
        pass

    def on_rpl_unaway(self, msg):
        pass

    def on_rpl_nowaway(self, msg):
        pass

    def on_rpl_whoisuser(self, msg):
        pass

    def on_rpl_whoisserver(self, msg):
        pass

    def on_rpl_whoisoperator(self, msg):
        pass

    def on_rpl_whowasuser(self, msg):
        pass

    def on_rpl_endofwho(self, msg):
        pass

    def on_rpl_whoischanop(self, msg):
        pass

    def on_rpl_whoisidle(self, msg):
        pass

    def on_rpl_endofwhois(self, msg):
        pass

    def on_rpl_whoischannels(self, msg):
        pass

    def on_rpl_liststart(self, msg):
        pass

    def on_rpl_list(self, msg):
        pass

    def on_rpl_listend(self, msg):
        pass

    def on_rpl_channelmodeis(self, msg):
        pass

    def on_rpl_notopic(self, msg):
        pass

    def on_rpl_topic(self, msg):
        pass

    def on_rpl_inviting(self, msg):
        pass

    def on_rpl_summoning(self, msg):
        pass

    def on_rpl_version(self, msg):
        pass

    def on_rpl_whoreply(self, msg):
        pass

    def on_rpl_namreply(self, msg):
        """
        List of names in a channel received (numeric 353).

        Args:
            msg(IrcMessage): Message with all users in the channel from the server.
        """
        channelMatch = re.search(r" = (\S+) :", msg.rawMsg)
        names = []
        if channelMatch:
            channel = channelMatch.group(1).lower()
            names = msg.rawMsg.split(channelMatch.group(0))[1]
            names = names.split(" ")
            prefixes = "".join(self.server.prefixes.values())

            self.channels[channel].users = []
            for n in names:
                name = n.lstrip(prefixes).lower()  # TODO: Add prefixes to User categories.
                self.channels[channel].users.append(name)
                if name not in self.server.users:
                    self.server.users[name] = User(n.lstrip(prefixes), self.server)

                self.server.users[name].channels.append(channel)

            logger.debug("self.server.users dict = {}".format(self.server.users))
            logger.debug("{} userlist: = {}".format(channel, self.channels[channel].users))

    def on_rpl_killdone(self, msg):
        pass

    def on_rpl_closing(self, msg):
        pass

    def on_rpl_closeend(self, msg):
        pass

    def on_rpl_endofnames(self, msg):
        pass

    def on_rpl_links(self, msg):
        pass

    def on_rpl_endoflinks(self, msg):
        pass

    def on_rpl_banlist(self, msg):
        pass

    def on_rpl_endofbanlist(self, msg):
        pass

    def on_rpl_endofwhowas(self, msg):
        pass

    def on_rpl_info(self, msg):
        pass

    def on_rpl_motd(self, msg):
        pass

    def on_rpl_infostart(self, msg):
        pass

    def on_rpl_endofinfo(self, msg):
        pass

    def on_rpl_motdstart(self, msg):
        pass

    def on_rpl_endofmotd(self, msg):
        """
        Signals the end of the Message of the Day. Bot's cue to authenticate itself and join channels.
        """
        self.identify()
        for chan in self.channels:
            self.join(chan)

    def on_rpl_youreoper(self, msg):
        pass

    def on_rpl_rehashing(self, msg):
        pass

    def on_rpl_myportis(self, msg):
        pass

    def on_rpl_time(self, msg):
        pass

    def on_rpl_usersstart(self, msg):
        pass

    def on_rpl_users(self, msg):
        pass

    def on_rpl_endofusers(self, msg):
        pass

    def on_rpl_nousers(self, msg):
        pass

    def on_err_nosuchnick(self, msg):
        pass

    def on_err_nosuchserver(self, msg):
        pass

    def on_err_nosuchchannel(self, msg):
        pass

    def on_err_cannotsendtochan(self, msg):
        pass

    def on_err_toomanychannels(self, msg):
        pass

    def on_err_wasnosuchnick(self, msg):
        pass

    def on_err_toomanytargets(self, msg):
        pass

    def on_err_noorigin(self, msg):
        pass

    def on_err_norecipient(self, msg):
        pass

    def on_err_notexttosend(self, msg):
        pass

    def on_err_notoplevel(self, msg):
        pass

    def on_err_wildtoplevel(self, msg):
        pass

    def on_err_unknowncommand(self, msg):
        pass

    def on_err_nomotd(self, msg):
        pass

    def on_err_noadmininfo(self, msg):
        pass

    def on_err_fileerror(self, msg):
        pass

    def on_err_nonicknamegiven(self, msg):
        pass

    def on_err_erroneusnickname(self, msg):
        pass

    def on_err_nicknameinuse(self, msg):
        pass

    def on_err_nickcollision(self, msg):
        pass

    def on_err_usernotinchannel(self, msg):
        pass

    def on_err_notonchannel(self, msg):
        pass

    def on_err_useronchannel(self, msg):
        pass

    def on_err_nologin(self, msg):
        pass

    def on_err_summondisabled(self, msg):
        pass

    def on_err_usersdisabled(self, msg):
        pass

    def on_err_notregistered(self, msg):
        pass

    def on_err_needmoreparams(self, msg):
        pass

    def on_err_alreadyregistred(self, msg):
        pass

    def on_err_nopermforhost(self, msg):
        pass

    def on_err_passwdmismatch(self, msg):
        pass

    def on_err_yourebannedcreep(self, msg):
        pass

    def on_err_youwillbebanned(self, msg):
        pass

    def on_err_keyset(self, msg):
        pass

    def on_err_channelisfull(self, msg):
        pass

    def on_err_unknownmode(self, msg):
        pass

    def on_err_inviteonlychan(self, msg):
        pass

    def on_err_bannedfromchan(self, msg):
        pass

    def on_err_badchannelkey(self, msg):
        pass

    def on_err_badchanmask(self, msg):
        pass

    def on_err_noprivileges(self, msg):
        pass

    def on_err_chanoprivsneeded(self, msg):
        pass

    def on_err_cantkillserver(self, msg):
        pass

    def on_err_nooperhost(self, msg):
        pass

    def on_err_noservicehost(self, msg):
        pass

    def on_err_umodeunknownflag(self, msg):
        pass

    def on_err_usersdontmatch(self, msg):
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

        self.users = {}  # {"username": User()}

    def __str__(self):
        return self.name


class Channel(object):
    RESET_INTERVAL = 2  # How many seconds to wait before resetting certain values (see reset_values).
    
    def __init__(self, name, isPM=False):
        self.name = name
        self.users = []  # ["username"]
        self.messages = []  # [(raw_message1, time1), (raw_message2, time2)]
        self.isPM = isPM
        self.quiet = False
        self.game = None
        self.song = None

        if not self.isPM:
            ## Determines the limit on greet/gossip messages, resets at an interval:
            self.joinedNum = 0
            self.leftNum = 0
            resetti = threading.Timer(self.RESET_INTERVAL, self.reset_values)
            resetti.daemon = True
            resetti.start()

    def __str__(self):
        return self.name

    def reset_values(self):
        self.joinedNum = 0
        self.leftNum = 0


class User(object):
    ## Categories
    OP = "o"
    HALF_OP = "h"
    VOICED = "v"
    
    def __init__(self, nickname, server):
        self.nickname = nickname
        self.idle = False  # True if hasn't talked in any channel for > 5 min?
        self.ignore = False
        self.messages = []  # [IrcMessage(),]
        self.server = server  # Server()
        self.channels = []

        try:
            self.userID = 1  # TO-DO: Fetch user ID from database
        except IndexError:  # User not in user file.
            self.userID = ALL

    def __str__(self):
        return self.nickname
    
    @property
    def categories(self):
        """
        Retrieves the categories the user falls in.
        """
        cats = self._categories
        try:
            # TO-DO: Fetch user's categories from database
            cats.split(lineparser.get_setting("Variables", "category_split"))
        except IndexError:
            pass

        return cats

    @categories.setter
    def categories(self, value):
        self._categories = value

    def custom_nick(self, channel="", includeGeneric=True, includeUsername=True):
        """
        Returns a nickname for the user.
        """
        userFilter = [self.userID, ALL]
        userFilter = lineparser.get_setting("Variables", "category_split").join(set(userFilter))
        if includeGeneric:
            filters = {"category": lineparser.get_setting("Variables", "category_split").join(self.categories), "users": userFilter}
        else:
            filters = {"users": self.nickname}
        filters["servers"] = ",".join(set(self.server, ALL))
        filters["channels"] = ",".join(set(channel, ALL))

        ## TO-DO: Fetch nicknames for user.
        """
        keys = subjectFile.get_keys(filters)
        nicks = [subjectFile.get_field(k, "subject") for k in keys]
        if includeUsername:
            nicks.append(self.nickname)
        
        return random.choice(nicks)
        """


def test():
    print(type(IrcMessage("sandwiché").__str__()))
    print("sandwiché".encode("utf-8"))
    print("sandwiché")
    print(type("sandwiché"))


if "__main__" == __name__:
    test()
