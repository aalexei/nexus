##
## Copyright 2010-2019 Alexei Gilchrist
##
## This file is part of Nexus.
##
## Nexus is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Nexus is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Nexus.  If not, see <http://www.gnu.org/licenses/>.

import logging, io, code, sys, re
from . import graphydb

## ------------------------------------------------------------------------
## leaving this as boilerplate for creating an interactive interpreter:
class Interpreter(code.InteractiveInterpreter):
## ------------------------------------------------------------------------

    def __init__(self, initmethods={}):

        methods = {}

        methods.update(initmethods)
        super().__init__(methods)

    def reset(self):

        self.locals = {}

    def run(self, cmd):

        out = io.StringIO()
        err = io.StringIO()

        sys.stdout = out
        sys.stderr = err

        self.runcode(cmd)

        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

        err = err.getvalue()
        if len(err) > 0:
            logging.error(err)

        return out.getvalue()


## ------------------------------------------------------------------------
class FilterInterpreter(code.InteractiveInterpreter):
    '''
    Everytime the filter is executed an instance of this class is created to handle the request
    '''
## ------------------------------------------------------------------------

    def __init__(self, scene):

        methods = {
                'find': self.find,
                'tagged': self.tagged,
                'all': self.all,
                'selected': self.selected,
                }

        ## need to pass the scene to these methods
        self.scene = scene

        super().__init__(methods)

    def run(self, cmd):
        '''
        wrap the runcode to handle errors and output
        '''

        out = io.StringIO()
        err = io.StringIO()

        sys.stdout = out
        sys.stderr = err

        self.runcode(cmd)

        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

        err = err.getvalue()
        if len(err) > 0:
            logging.error(err)

        return out.getvalue()

    def find(self, *args, **keys):
        return Collection(self.scene).find(*args, **keys)

    def tagged(self, *args, **keys):
        return Collection(self.scene).tagged(*args, **keys)

    def all(self):
        return Collection(self.scene)

    def selected(self):
        return Collection(self.scene).selected()


## ------------------------------------------------------------------------
class Collection(set):
## ------------------------------------------------------------------------

    def __init__(self, scene, elements=None):
        self.scene = scene
        if elements is None:
            ## start each collection will all stems
            elements = set(scene.allChildStems(includeroot=False))
        super().__init__(elements)

    ##
    ## filters with set
    ##

    def all(self):
        'this just resets to all stems again'
        return Collection(self.scene)

    def find(self, title=None, tag=None):
        'filter set down'

        matching = set([])

        titlematch = True
        tagmatch = True
        for target in self:
            if tag is not None:
                tags = ' '.join(target.getTags())
                tagmatch = re.search(tag, tags, re.I) is not None

            if title is not None:
                titles = ' '.join(target.titles())
                titlematch = re.search(title, titles, re.I) is not None

            if tagmatch and titlematch:
                matching.add(target)

        return Collection(self.scene, matching)

    def tagged(self, tagre=''):
        return self.find(tag=tagre)

    def selected(self):
        'filter to selected stems within set'

        matching = set([])

        for stem in self:
            if stem.isSelected():
                matching.add(stem)

        return Collection(self.scene, matching)

    def up(self):
        'extend the collection up the tree'

        extend = set([])

        for stem in self:
            for s in stem.allParentStems():
                extend.add(s)

        return Collection(self.scene, self | extend)

    def down(self):
        'extend the collection down the tree'

        extend = set([])

        for stem in self:
            for s in stem.allChildStems():
                extend.add(s)

        return Collection(self.scene, self | extend)

    ##
    ## actions with set
    ##

    def alpha(self,a=1.0):
        batch = graphydb.generateUUID()
        for stem in self:
            if a < 1:
                stem.node['opacity'] = a
            else:
                stem.node.discard('opacity')
            stem.node.save(batch=batch, setchange=True)
            stem.renew(create=False, position=False, children=False)
        return self

    def hide(self):
        batch = graphydb.generateUUID()
        allchildren = set()
        for stem in self:
            allchildren |= set(stem.allChildStems())
            stem.node['hide'] = True
            stem.node.save(batch=batch, setchange=True)
        for stem in self:
            if stem not in allchildren:
                stem.renew(create=False, position=False, recurse=False)
        return self

    def show(self):
        batch = graphydb.generateUUID()
        allchildren = set()
        for stem in self:
            allchildren |= set(stem.allChildStems())
            stem.node.discard('hide')
            stem.node.save(batch=batch, setchange=True)
        for stem in self:
            if stem not in allchildren:
                stem.renew(create=False)
        return self

    def select(self):
        for stem in self:
            stem.setSelected(True)
        return self

    def deselect(self):
        for stem in self:
            stem.setSelected(False)
        return self

    def scale(self, scale):

        for stem in self:
            transform = stem.transform()
            currentscale = transform.m11()
            transform.scale(scale/currentscale,scale/currentscale)
            stem.setTransform(transform)
        for stem in self:
            stem.updateStem()

        return self

    @classmethod
    def _wrap_methods(cls, names):
        '''
        The following is so set operations return Collection class with a reference to the scene
        '''
        def wrap_method_closure(name):
            def inner(self, *args):
                result = Collection(self.scene, getattr(super(cls, self), name)(*args))
                return result
            inner.fn_name = name
            setattr(cls, name, inner)
        for name in names:
            wrap_method_closure(name)

Collection._wrap_methods(['__ror__', 'difference_update', '__isub__',
    'symmetric_difference', '__rsub__', '__and__', '__rand__', 'intersection',
    'difference', '__iand__', 'union', '__ixor__',
    'symmetric_difference_update', '__or__', 'copy', '__rxor__',
    'intersection_update', '__xor__', '__ior__', '__sub__',
])


## for testing purposes ....
if __name__ == '__main__':


    import sys
