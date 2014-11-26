#!/usr/bin/env python

# Copyright (C) 2014  Eddie Antonio Santos
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

try:
    from unnaturalcode.http import unnaturalhttp
except ImportError:
    import sys, os
    # Oiugh. 
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from unnaturalcode.http import unnaturalhttp

from flask import Flask

app = Flask(__name__)
app.register_blueprint(unnaturalhttp)
app.run(host='0.0.0.0')
