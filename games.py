import random
import time
import lineparser


class Game(object):
    def __init__(self, gameTitle):
        self.players = {}
        self.started = False
        self.gameTitle = gameTitle

    def add_player(self, player, channelUsers):
        if player.name.lower() in self.players:
            return "alreadyin"
        if player.name.lower() not in [n.lower() for n in channelUsers]:
            player = None
            return "nonexistent"
        self.players[player.name.lower()] = None
        self.players[player.name.lower()] = player

        return True

    def remove_player(self, playerName):
        if playerName.lower() in self.players:
            del self.players[playerName.lower()]
            return True
        return False
    
    
### === Hijack === ###
class HijackGame(Game):
    def __init__(self):
        Game.__init__(self, lineparser.get_settting("Titles", "game-hijack"))

    def get_average_HP(self):
        average = 0
        healthyPlayers = []
        for p in self.players:
            if self.players[p].health > 0:
                average = average + self.players[p].health
                healthyPlayers.append(self.players[p])
        average /= len(healthyPlayers)

        return int(round(average, 1))

    def process_command(self, nick, msg, channelUsers):
        self.gameTitle = lineparser.get_setting("Titles", "game-hijack")
        output = []
        
        msg = msg.strip()
        cmd = msg.split(" ")[0]
        args = []
        if len(msg.split(" ")) > 1:
            args = msg.split(" ")
            args.remove(args[0])
        if lineparser.get_setting("GameCommands", "add_player") == cmd.lower():
            if args:
                for a in args:
                    name = a.split(lineparser.get_setting("Splitters", "hijack-subparams"))[0]
                    health = 100
                    if self.started:
                        try:
                            health = self.get_average_HP()
                        except (ValueError, ZeroDivisionError):
                            pass
                    try:
                        health = int(a.split(lineparser.get_setting("Splitters", "hijack-subparams"))[1])
                    except (IndexError, ValueError):
                        health = 100
                    
                    if "alreadyin" == self.add_player(HijackPlayer(name, health), channelUsers):
                        output.append((lineparser.get_setting("Inform", "hijack-playeralreadyin").replace(lineparser.get_setting("Substitutions", "sendnick"), name), 1))
                    elif "nonexistent" == self.add_player(HijackPlayer(name, health), channelUsers):
                        nopeMsg = lineparser.get_setting("Inform", "hijack-nonexistentplayer")
                        nopeMsg = nopeMsg.replace(lineparser.get_setting("Substitutions", "sendnick"), name)
                        output.append((nopeMsg, 1))
                    else:
                        output.append(("{nick} joined the game with {hp} health points.".format(nick=name,
                                                                                                hp=health), 1))
                output.append(("Number of people playing {g}: {num}".format(g=self.gameTitle,
                                                                            num=str(len(self.players))), 0))
        elif self.init["GameCommands"]["attack"] == cmd.lower():
            if not self.started:
                output.append((lineparser.get_setting("Inform", "hijack-notstarted"), 0))
            else:
                if args:
                    who = args[0]
                    if who.lower() in self.players:
                        if self.players[who.lower()].health <= 0:
                            overkillMsg = random.choice(lineparser.get_setting("Choices", "hijack-tryoverkill").split(lineparser.get_setting("Splitters", "choices-hijack")))
                            output.append((overkillMsg.replace(lineparser.get_setting("Substitutions", "sendnick"), who), 0))
                        else:
                            amountTimes = 1
                            sides = 20
                            try:
                                amountTimes = int(args[1].split("d")[0])
                                if amountTimes > 5:
                                    amountTimes = 5
                            except (IndexError, ValueError):
                                pass
                            try:
                                sides = int(args[1].split("d")[1])
                            except (IndexError, ValueError):
                                pass
                            
                            for _ in range(amountTimes):
                                damage = self.players[nick.lower()].getAttackPower(sides)
                                self.players[who.lower()].health -= damage
                                output.append(("{who} took {d} damage.".format(self.players[who.lower()].name,
                                                                               d=str(damage)), 1))
                            thanksMsg = random.choice(lineparser.get_setting("Choices", "hijack-thanks").split(lineparser.get_setting("Splitters", "choices-hijack")))
                            thanksMsg = thanksMsg.replace(lineparser.get_setting("Substitutions", "sendnick"), nick)
                            output.append(("{who} now has {h} health points. {thanks}".format(who=self.players[who.lower()].name,
                                                                                              h=str(self.players[who.lower()].health),
                                                                                              thanks=thanksMsg), 0))
        elif self.init["GameCommands"]["build"] == cmd.lower():
            if not self.started:
                output.append((lineparser.get_setting("Inform", "hijack-notstarted"), 0))
            else:
                if nick.lower() in self.players:
                    if self.players[nick.lower()].buildCharge():
                        buildMsg = random.choice(lineparser.get_setting("Choices", "hijack-buildmsg").split(lineparser.get_setting("Splitters", "choices-hijack")))
                        buildMsg = buildMsg.replace(lineparser.get_setting("Substitutions", "sendnick"), nick)
                        output.append((buildMsg, 0))
                    else:
                        output.append((lineparser.get_setting("Inform", "hijack-maxcharge"), 0))
        elif lineparser.get_setting("GameCommands", "get_average_HP") == cmd.lower():
            if self.players:
                output.append(("Average amount of health points across all players: {hp}".format(hp=str(self.get_average_HP())), 0))
            else:
                output.append((lineparser.get_setting("Inform", "hijack-noplayers"), 0))
        elif lineparser.get_setting("GameCommands", "gethp") == cmd.lower():
            if args:
                for who in args:
                    if who.lower() in self.players:
                        output.append(("{who} has {hp} health points.".format(who=self.players[who.lower()].name,
                                                                              hp=str(self.players[who.lower()].health)), 1))
            else:
                if self.players:
                    output.append(("Average amount of health points across all players: {hp}".format(hp=str(self.get_average_HP())), 0))
                else:
                    output.append((lineparser.get_setting("Inform", "hijack-noplayers"), 0))
        elif lineparser.get_setting("GameCommands", "leave") == cmd.lower():
            who = []
            hasLeft = False
            if args:
                who = args
            else:
                who = [nick]
            for w in who:
                if self.remove_player(w):
                    leftMsg = random.choice(lineparser.get_setting("Choices", "hijack-leavegame").split(lineparser.get_setting("Splitters", "choices-hijack")))
                    leftMsg = leftMsg.replace(lineparser.get_setting("Substitutions", "sendnick"), w)
                    output.append((leftMsg, 1))
                    hasLeft = True
            if hasLeft:
                output.append(("Number of people playing {g}: {num}".format(g=self.gameTitle,
                                                                            num=str(len(self.players))), 0))
        elif self.init["GameCommands"]["resetcharge"] == cmd.lower():
            if args:
                for who in args:
                    resetMsg = ""
                    if who.lower() in self.players:
                        self.players[who.lower()].attackCharge = 0
                        resetMsg = random.choice(lineparser.get_setting("Choices", "hijack-resetcharge").split(lineparser.get_setting("Splitters", "choices-hijack")))
                        resetMsg = resetMsg.replace(lineparser.get_setting("Substitutions", "sendnick"), self.players[who.lower()].name)
                        output.append((resetMsg, 1))
                    else:
                        resetMsg = random.choice(lineparser.get_setting("Inform", "hijack-nosuchplayer").split(lineparser.get_setting("Splitters", "choices-hijack")))
                        resetMsg = resetMsg.replace(lineparser.get_setting("Substitutions", "sendnick"), self.players[who.lower()].name)
                        output.append((resetMsg, 1))
            else:
                output.append((lineparser.get_setting("Inform", "hijack-howtoresetcharge"), 0))
        elif lineparser.get_setting("GameCommands", "sethp") == cmd.lower():
            if args:
                for who in args:
                    name = who.split(lineparser.get_setting("Splitters", "hijack-subparams"))[0].lower()
                    if len(who.split(lineparser.get_setting("Splitters", "hijack-subparams"))[0].lower()) > 1:
                        try:
                            if name in self.players:
                                newHealth = who.split(lineparser.get_setting("Splitters", "hijack-subparams"))[1]
                                if "-" in newHealth:
                                    newHealth = int(round(newHealth.translate(None, "-")))
                                    self.players[name.lower()].health -= newHealth
                                elif "+" in newHealth:
                                    newHealth = int(round(newHealth.translate(None, "+")))
                                    self.players[name.lower()].health += newHealth
                                else:
                                    self.players[name.lower()].health = newHealth
                                output.append(("{n} now has {hp} health points.".format(n=self.players[name.lower()].name,
                                                                                        hp=newHealth), 0))
                        except TypeError:
                            output.append((lineparser.get_setting("Inform", "hijack-errorsethp").replace(lineparser.get_setting("Substitutions", "sendnick"), self.players[name.lower()].name), 0))
                    else:
                        pass
        elif lineparser.get_setting("Commands", "startplaying") == cmd.lower():
            if self.started:
                pass
            else:
                self.started = True
                output.append((lineparser.get_setting("Inform", "hijack-startplaying"), 0))
            
        return output
                    

class HijackPlayer(object):
    def __init__(self, name, health):
        self.name = name
        self.health = int(health)
        self.attackCharge = 0

    def build_charge(self):
        if self.attackCharge < 25:
            self.attackCharge += 5
            return True
        else:
            return False

    def get_attack_power(self, sides = 20):
        power = random.randint(1, sides) + self.attackCharge
        self.attackCharge = 0
        return power


### === Hot Potato Grenade === ###
class HotPotatoGame(Game):
    def __init__(self):
        Game.__init__(self, lineparser.get_setting("Titles", "game-hotpotato"))
        self.currentHolder = None
        self.stopTimer = {"master": False, "single": False}

    def process_command(self, nick, msg, channelUsers):
        self.gameTitle = lineparser.get_setting("Titles", "game-hotpotato")
        output = []
        
        msg = msg.strip()
        cmd = msg.split(" ")[0]
        args = []
        if len(msg.split(" ")) > 1:
            args = msg.split(" ")
            args.remove(args[0])

        if lineparser.get_setting("GameCommands", "add_player").lower() == cmd.lower():
            if args:
                for arg in args:
                    if "alreadyin" == self.add_player(HotPotatoPlayer(arg,), channelUsers):
                        output.append((lineparser.get_setting("Inform", "hijack-playeralreadyin").replace(lineparser.get_setting("Substitutions", "sendnick"), name), 1))
                    elif "nonexistent" == self.add_player(HijackPlayer(name, health), channelUsers):
                        nopeMsg = lineparser.get_setting("Inform", "hotpotato-nonexistentplayer")
                        nopeMsg = nopeMsg.replace(lineparser.get_setting("Substitutions", "sendnick"), name)
                        output.append((nopeMsg, 1))
                    else:
                        output.append(("{nick} joined the game.".format(nick=name,), 1))
        elif lineparser.get_setting("GameCommands", "leave").lower() == cmd.lower():
            who = []
            hasLeft = False
            if args:
                who = args
            else:
                who = [nick]
            for w in who:
                if self.remove_player(w):
                    leftMsg = random.choice(lineparser.get_setting("Choices", "hijack-leavegame").split(lineparser.get_setting("Splitters", "choices-hijack")))
                    leftMsg = leftMsg.replace(lineparser.get_setting("Substitutions", "sendnick"), w)
                    output.append((leftMsg, 1))
                    hasLeft = True
            if hasLeft:
                output.append(("Number of people playing {g}: {num}".format(g=self.gameTitle,
                                                                            num=str(len(self.players))), 0))
        elif lineparser.get_setting("Commands", "startplaying").lower() == cmd.lower():
            if self.started:
                pass
            elif self.players:
                self.started = True
                self.currentHolder = random.choice(list(self.players.values()))
                output.append((lineparser.get_setting("Inform", "hotpotato-startplaying"), 1))
                output.append((lineparser.get_setting("Choices", "hotpotato-startpass").replace(lineparser.get_setting("Substitutions", "sendNick"), self.currentHolder.name), 0))
            else:
                ## No one's playing.
                pass

        elif lineparser.get_setting("GameCommands", "hotpotato-pass").lower() == cmd.lower():
            if 1 <= len(args):
                if args[0].lower() in self.players:
                    self.currentHolder = self.players[args[0].lower()]
                
    def timer(seconds, whichTimer):
        output = []
        while 0 < seconds:
            if self.stopTimer[whichTimer]:
                return
            pass

        output.append(("Boom.", 1))
        output.append(("Bye, {nick}".format(nick=self.currentHolder.name), 0))
        self.remove_player(self.currentHolder.name)

        
class HotPotatoPlayer(object):
    def __init__(self, name):
        self.name = name


if "__main__" == __name__:
    Game("Stuff")
