"""Spells for optimizing nif files."""

# --------------------------------------------------------------------------
# ***** BEGIN LICENSE BLOCK *****
#
# Copyright (c) 2007-2008, NIF File Format Library and Tools.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#
#    * Redistributions in binary form must reproduce the above
#      copyright notice, this list of conditions and the following
#      disclaimer in the documentation and/or other materials provided
#      with the distribution.
#
#    * Neither the name of the NIF File Format Library and Tools
#      project nor the names of its contributors may be used to endorse
#      or promote products derived from this software without specific
#      prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# ***** END LICENSE BLOCK *****
# --------------------------------------------------------------------------

from itertools import izip

from PyFFI.Formats.NIF import NifFormat
from PyFFI.Utils import TriStrip
import PyFFI.Spells
import PyFFI.Spells.NIF
import PyFFI.Spells.NIF.fix

# set flag to overwrite files
__readonly__ = False

# example usage
__examples__ = """* Standard usage:

    python niftoaster.py optimize /path/to/copy/of/my/nifs

* Optimize, but do not merge NiMaterialProperty blocks:

    python niftoaster.py optimize --exclude=NiMaterialProperty /path/to/copy/of/my/nifs
"""

class SpellCleanRefLists(PyFFI.Spells.NIF.NifSpell):
    """Remove empty and duplicate entries in reference lists."""

    SPELLNAME = "opt_cleanreflists"
    READONLY = False

    def datainspect(self):
        # so far, only reference lists in NiObjectNET blocks, NiAVObject
        # blocks, and NiNode blocks are checked
        return (self.inspectblocktype(NifFormat.NiObjectNET)
        # see MadCat221's metstaff.nif:
        # merging data on PSysMeshEmitter affects particle system
        # so do not merge child links on this nif (probably we could still
        # merge other things: this is just a quick hack to make sure the
        # optimizer won't do anything wrong)
                and not self.inspectblocktype(NifFormat.NiPSysMeshEmitter))

    def branchinspect(self, branch):
        # only inspect the NiObjectNET branch
        return isinstance(branch, NifFormat.NiObjectNET)

    def cleanreflist(self, reflist, category):
        """Return a cleaned copy of the given list of references."""
        # delete empty and duplicate references
        cleanlist = []
        for ref in reflist:
            if ref is None:
                self.toaster.msg("removing empty %s reference" % category)
            elif ref in cleanlist:
                self.toaster.msg("removing duplicate %s reference" % category)
            else:
                cleanlist.append(ref)
        # done
        return cleanlist

    def branchentry(self, branch):
        if isinstance(branch, NifFormat.NiObjectNET):
            # clean extra data
            branch.setExtraDatas(
                self.cleanreflist(branch.getExtraDatas(), "extra"))
        if isinstance(branch, NifFormat.NiAVObject):
            # clean properties
            branch.setProperties(
                self.cleanreflist(branch.getProperties(), "property"))
        if isinstance(branch, NifFormat.NiNode):
            # clean children
            branch.setChildren(
                self.cleanreflist(branch.getChildren(), "child"))
            # clean effects
            branch.setEffects(
                self.cleanreflist(branch.getEffects(), "effect"))
        # always recurse further
        return True

class SpellMergeDuplicates(PyFFI.Spells.NIF.NifSpell):

    SPELLNAME = "opt_mergeduplicates"
    READONLY = False

    def __init__(self, *args, **kwargs):
        PyFFI.Spells.NIF.NifSpell.__init__(self, *args, **kwargs)
        # list of all branches visited so far
        self.branches = []

    def datainspect(self):
        # see MadCat221's metstaff.nif:
        # merging data on PSysMeshEmitter affects particle system
        # so do not merge shapes on this nif (probably we could still
        # merge other things: this is just a quick hack to make sure the
        # optimizer won't do anything wrong)
        try:
            return not self.data.header.hasBlockType(NifFormat.NiPSysMeshEmitter)
        except ValueError:
            # when in doubt, do the spell
            return True

    def branchinspect(self, branch):
        # only inspect the NiObjectNET branch (merging havok can mess up things)
        return isinstance(branch, (NifFormat.NiObjectNET,
                                   NifFormat.NiGeometryData))

    def branchentry(self, branch):
        for otherbranch in self.branches:
            if (branch is not otherbranch and
                branch.isInterchangeable(otherbranch)):
                # skip properties that have controllers (the
                # controller data cannot always be reliably checked,
                # see also issue #2106668)
                if (isinstance(branch, NifFormat.NiProperty)
                    and branch.controller):
                    continue
                # interchangeable branch found!
                self.toaster.msg("removing duplicate branch")
                self.data.replaceGlobalTreeBranch(branch, otherbranch)
                # branch has been replaced, so no need to recurse further
                return False
        else:
            # no duplicate found, add to list of visited branches
            self.branches.append(branch)
            # continue recursion
            return True

class SpellOptimize(
    PyFFI.Spells.SpellGroupSeries(
        PyFFI.Spells.SpellGroupParallel(
            SpellCleanRefLists,
            PyFFI.Spells.NIF.fix.SpellDetachHavokTriStripsData,
            PyFFI.Spells.NIF.fix.SpellFixTexturePath,
            PyFFI.Spells.NIF.fix.SpellClampMaterialAlpha),
        SpellMergeDuplicates)):
    """Global fixer and optimizer spell."""
    SPELLNAME = "optimize_experimental"

def optimizeTriBasedGeom(block, striplencutoff = 10.0, stitch = True):
    """Optimize a NiTriStrips or NiTriShape block:
      - remove duplicate vertices
      - stripify if strips are long enough
      - recalculate skin partition
      - recalculate tangent space 

    @param block: The shape block.
    @type block: L{NifFormat.NiTriBasedGeom}
    @param striplencutoff: Minimum average length for strips (below this
        length the block is triangulated).
    @type striplencutoff: float
    @param stitch: Whether to stitch strips or not.
    @type stitch: bool
    @return: An optimized version of the shape.

    @todo: Limit the length of strips (see operation optimization mod for
        Oblivion!)
    """
    print("optimizing block '%s'" % block.name)

    # cover degenerate case
    if block.data.numVertices < 3:
        print "  less than 3 vertices: removing block"
        return None

    data = block.data

    print "  removing duplicate vertices"
    v_map = [0 for i in xrange(data.numVertices)] # maps old index to new index
    v_map_inverse = [] # inverse: map new index to old index
    k_map = {} # maps hash to new vertex index
    index = 0  # new vertex index for next vertex
    for i, vhash in enumerate(data.getVertexHashGenerator()):
        try:
            k = k_map[vhash]
        except KeyError:
            # vertex is new
            k_map[vhash] = index
            v_map[i] = index
            v_map_inverse.append(i)
            index += 1
        else:
            # vertex already exists
            v_map[i] = k
    del k_map

    new_numvertices = index
    print("  (num vertices was %i and is now %i)"
          % (len(v_map), new_numvertices))
    # copy old data
    oldverts = [[v.x, v.y, v.z] for v in data.vertices]
    oldnorms = [[n.x, n.y, n.z] for n in data.normals]
    olduvs   = [[[uv.u, uv.v] for uv in uvset] for uvset in data.uvSets]
    oldvcols = [[c.r, c.g, c.b, c.a] for c in data.vertexColors]
    if block.skinInstance: # for later
        oldweights = block.getVertexWeights()
    # set new data
    data.numVertices = new_numvertices
    if data.hasVertices:
        data.vertices.updateSize()
    if data.hasNormals:
        data.normals.updateSize()
    data.uvSets.updateSize()
    if data.hasVertexColors:
        data.vertexColors.updateSize()
    for i, v in enumerate(data.vertices):
        old_i = v_map_inverse[i]
        v.x = oldverts[old_i][0]
        v.y = oldverts[old_i][1]
        v.z = oldverts[old_i][2]
    for i, n in enumerate(data.normals):
        old_i = v_map_inverse[i]
        n.x = oldnorms[old_i][0]
        n.y = oldnorms[old_i][1]
        n.z = oldnorms[old_i][2]
    for j, uvset in enumerate(data.uvSets):
        for i, uv in enumerate(uvset):
            old_i = v_map_inverse[i]
            uv.u = olduvs[j][old_i][0]
            uv.v = olduvs[j][old_i][1]
    for i, c in enumerate(data.vertexColors):
        old_i = v_map_inverse[i]
        c.r = oldvcols[old_i][0]
        c.g = oldvcols[old_i][1]
        c.b = oldvcols[old_i][2]
        c.a = oldvcols[old_i][3]
    del oldverts
    del oldnorms
    del olduvs
    del oldvcols

    # update vertex indices in strips/triangles
    if isinstance(block, NifFormat.NiTriStrips):
        for strip in data.points:
            for i in xrange(len(strip)):
                strip[i] = v_map[strip[i]]
    elif isinstance(block, NifFormat.NiTriShape):
        for tri in data.triangles:
            tri.v1 = v_map[tri.v1]
            tri.v2 = v_map[tri.v2]
            tri.v3 = v_map[tri.v3]

    # stripify trishape/tristrip
    if isinstance(block, NifFormat.NiTriStrips):
        print "  recalculating strips"
        origlen = sum(i for i in data.stripLengths)
        data.setTriangles(data.getTriangles())
        newlen = sum(i for i in data.stripLengths)
        print "  (strip length was %i and is now %i)" % (origlen, newlen)
    elif isinstance(block, NifFormat.NiTriShape):
        print "  stripifying"
        block = block.getInterchangeableTriStrips()
        data = block.data
    # average, weighed towards large strips
    if isinstance(block, NifFormat.NiTriStrips):
        # note: the max(1, ...) is to avoid ZeroDivisionError
        avgstriplen = float(sum(i * i for i in data.stripLengths)) \
            / max(1, sum(i for i in data.stripLengths))
        print "  (average strip length is %f)" % avgstriplen
        if avgstriplen < striplencutoff:
            print("  average strip length less than %f so triangulating"
                  % striplencutoff)
            block = block.getInterchangeableTriShape()
        elif stitch:
            print("  stitching strips (using %i stitches)"
                  % len(data.getStrips()))
            data.setStrips([TriStrip.stitchStrips(data.getStrips())])

    # update skin data
    if block.skinInstance:
        print "  update skin data vertex mapping"
        skindata = block.skinInstance.data
        newweights = []
        for i in xrange(new_numvertices):
            newweights.append(oldweights[v_map_inverse[i]])
        for bonenum, bonedata in enumerate(skindata.boneList):
            w = []
            for i, weightlist in enumerate(newweights):
                for bonenum_i, weight_i in weightlist:
                    if bonenum == bonenum_i:
                        w.append((i, weight_i))
            bonedata.numVertices = len(w)
            bonedata.vertexWeights.updateSize()
            for j, (i, weight_i) in enumerate(w):
                bonedata.vertexWeights[j].index = i
                bonedata.vertexWeights[j].weight = weight_i

        # update skin partition (only if block already exists)
        block._validateSkin()
        skininst = block.skinInstance
        skinpart = skininst.skinPartition
        if not skinpart:
            skinpart = skininst.data.skinPartition

        if skinpart:
            print "  updating skin partition"
            # use Oblivion settings
            block.updateSkinPartition(
                maxbonesperpartition = 18, maxbonespervertex = 4,
                stripify = True, verbose = 0)

    # update morph data
    for morphctrl in block.getControllers():
        if isinstance(morphctrl, NifFormat.NiGeomMorpherController):
            morphdata = morphctrl.data
            # skip empty morph data
            if not morphdata:
                continue
            # convert morphs
            print("  updating morphs")
            for morph in morphdata.morphs:
                # store a copy of the old vectors
                oldmorphvectors = [(vec.x, vec.y, vec.z)
                                   for vec in morph.vectors]
                for old_i, vec in izip(v_map_inverse, morph.vectors):
                    vec.x = oldmorphvectors[old_i][0]
                    vec.y = oldmorphvectors[old_i][1]
                    vec.z = oldmorphvectors[old_i][2]
                del oldmorphvectors
            # resize matrices
            morphdata.numVertices = new_numvertices
            for morph in morphdata.morphs:
                 morph.arg = morphdata.numVertices # manual argument passing
                 morph.vectors.updateSize()

    # recalculate tangent space (only if the block already exists)
    if block.find(block_name = 'Tangent space (binormal & tangent vectors)',
                  block_type = NifFormat.NiBinaryExtraData):
        print "  recalculating tangent space"
        block.updateTangentSpace()

    return block

def testRoot(root, **args):
    """Optimize the tree at root. This is the main entry point for the
    nifoptimize script.

    @param root: The root of the tree.
    @type root: L{NifFormat.NiObject}
    """
    # check which blocks to exclude
    exclude = args.get("exclude", [])

    # get list of all blocks
    block_list = [ block for block in root.tree(unique = True) ]

    print("optimizing geometries")
    # first update list of all blocks
    block_list = [ block for block in root.tree(unique = True) ]
    optimized_geometries = []
    for block in block_list:
        # optimize geometries
        if (isinstance(block, NifFormat.NiTriStrips) \
            and not "NiTriStrips" in exclude) or \
            (isinstance(block, NifFormat.NiTriShape) \
            and not "NiTriShape" in exclude):
            # already optimized? skip!
            if block in optimized_geometries:
                continue
            # optimize
            newblock = optimizeTriBasedGeom(block)
            optimized_geometries.append(block)
            # search for all locations of the block, and replace it
            if not(newblock is block):
                optimized_geometries.append(newblock)
                for otherblock in block_list:
                    if not(block in otherblock.getLinks()):
                        continue
                    if isinstance(otherblock, NifFormat.NiNode):
                        for i, child in enumerate(otherblock.children):
                            if child is block:
                                otherblock.children[i] = newblock
                    elif isinstance(otherblock, NifFormat.NiTimeController):
                        if otherblock.target is block:
                            otherblock.target = newblock
                    elif isinstance(otherblock, NifFormat.NiDefaultAVObjectPalette):
                        for i, avobj in enumerate(otherblock.objs):
                            if avobj.avObject is block:
                                avobj.avObject = newblock
                    elif isinstance(otherblock, NifFormat.bhkCollisionObject):
                        if otherblock.target is block:
                            otherblock.target = newblock
                    else:
                        raise RuntimeError(
                            "don't know how to replace block %s in %s"
                            % (block.__class__.__name__,
                               otherblock.__class__.__name__))

