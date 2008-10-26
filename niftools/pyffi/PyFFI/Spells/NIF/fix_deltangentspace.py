"""Spell to delete Oblivion tangent space blocks."""

from PyFFI.Formats.NIF import NifFormat
from PyFFI.Spells.NIF import NifSpell

class SpellDelTangentSpace(NifSpell):
    """Delete tangentspace if it is present."""

    SPELLNAME = "fix_deltangentspace"
    READONLY = False

    def datainspect(self):
        return self.data.header.hasBlockType(NifFormat.NiBinaryExtraData):

    def branchentry(self, branch):
        if isinstance(branch, NifFormat.NiTriBasedGeom):
            # does this block have tangent space data?
            for extra in branch.getExtraDatas():
                if isinstance(extra, NifFormat.NiBinaryExtraData):
                    if (extra.name ==
                        'Tangent space (binormal & tangent vectors)'):
                        self.toaster.msg("removing tangent space block")
                        branch.removeExtraData(extra)

