import os.path
import ConfigParser

class Settings(object):
    databaseDir = os.path.join(os.path.dirname(__file__), "database")
    
    def __init__(self, inputFile = os.path.join(databaseDir, "Settings.ini")):
        self.inputFile = inputFile
        self.keywords = {}
        self.readFile()

    def readFile(self):
        parser = ConfigParser.ConfigParser()
        parser.read(self.inputFile)
        for section in parser.sections():
           self.keywords[section] = {}
           for tup in parser.items(section):
               self.keywords[section][tup[0]] = ""
               self.keywords[section][tup[0]] = tup[1].decode("string-escape")
