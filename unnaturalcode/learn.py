#!/usr/bin/env python
#    Copyright 2013, 2014 Joshua Charles Campbell, Alex Wilson
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

import argparse

from unnaturalcode.ucUser import pyUser

def main():
  ucpy = pyUser()

  parser = argparse.ArgumentParser(description='Add known-good Python files to UnnaturalCode.')

  parser.add_argument('files', metavar='file', type=str, nargs='+',
                    help='A file to be added.')

  args = parser.parse_args()

  ucpy.sm.trainFile(args.files)

  ucpy.release()
  
if __name__ == '__main__':
    main()