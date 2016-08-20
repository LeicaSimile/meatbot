import logging
import irc
import lineparser


def main():
    lineparser.set_config("private\config.ini")
    testbot = irc.IrcBot(server="Esper",
                         host=lineparser.get_setting("Esper", "host"),
                         port=int(lineparser.get_setting("Esper", "port")),
                         channels=["#Meat'sTestingGround"],
                         botnick="MeatBotv2",
                         realname="MeatBot v.2 in testing phase. By MeatPuppet.",
                         auth=lineparser.get_setting("Esper", "account"),
                         password=lineparser.get_setting("Esper", "pass"),
                         )
    lineparser.set_config()
    testbot.run()

if "__main__" == __name__:
    main()
