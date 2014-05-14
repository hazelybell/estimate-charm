#    Copyright 2013 Joshua Charles Campbell
#
#    This file is part of UnnaturalCode.
#    
#    UnnaturalCode is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    UnnaturalCode is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with UnnaturalCode.  If not, see <http://www.gnu.org/licenses/>.

from ucUtil import *
from unnaturalCode import *
from pythonSource import *
from mitlmCorpus import *
from sourceModel import *

@singleton
class pyUser(object):
  
  def __init__(self):
      self.homeDir = os.path.expanduser("~")
      self.ucDir = os.getenv("UC_DATA", os.path.join(homeDir, ".unnaturalCode"))
      if not os.path.exists(ucDir):
        os.makedirs(ucDir)
      assert os.access(ucDir, os.X_OK & os.R_OK & os.W_OK)
      assert os.path.isdir(ucDir)
      
      self.readCorpus = os.path.join(ucDir, 'pyCorpus') 
      self.logFilePath = os.path.join(ucDir, 'pyLogFile')
      
      self.uc = unnaturalCode(logFilePath=self.logFilePath)
      self.cm = mitlmCorpus(readCorpus=self.readCorpus, writeCorpus=self.readCorpus, uc=self.uc)
      self.lm = pythonSource
      self.sm = sourceModel(cm=cm, language=self.lm)
    
