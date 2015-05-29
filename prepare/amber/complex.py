#  Copyright (C) 2012-2014  Hannes H Loeffler, Julien Michel
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
#  For full details of the license please see the COPYING file
#  that should have come with this distribution.

r"""
A class to build a complex.  Derives from Common.

The complex Setup class composes a complex object from a protein and a ligand
object.  The class can create an AMBER topology file for the complex.
"""


__revision__ = "$Id$"



import FESetup
from FESetup import const, errors, logger
import utils
from ligand import Ligand
from protein import Protein
from common import *



class Complex(Common):
    """The complex setup class."""

    from FESetup.prepare.ligutil import flex as lig_flex

    def __init__(self, protein, ligand, overwrite = False):
        """
        :param protein: the protein for complex composition
        :type protein: Protein or string
        :param ligand: the ligand for complex composition
        :type ligand: Ligand or string
        :param overwrite: overwrite files in the working directory from basedir
        :type overwrite: string
        :raises: SetupError
        """

        self.workdir = const.COMPLEX_WORKDIR

        # FIXME: ugly type checking!
        if type(protein) == str and type(ligand) == str:
            super(Complex, self).__init__(protein + const.PROT_LIG_SEP +
                                          ligand, '', self.workdir,
                                          overwrite)

            self.protein_file = protein
            self.ligand_file = ligand

            # FIXME: quick fix to allow dGprep to redo complex morph
            self.ligand = Ligand(ligand, '')

            return

        assert type(protein) == Protein
        assert type(ligand) == Ligand

        complex_name = protein.mol_name + const.PROT_LIG_SEP + ligand.mol_name
        super(Complex, self).__init__(complex_name, '', self.workdir,
                                      overwrite)

        # assume the original file to be the one from the original complex
        self.ligand_file = ligand.orig_file

        try:
            dst = os.path.join(ligand.topdir, self.workdir, complex_name)

            if not os.access(dst, os.F_OK):
                logger.write('Creating directory %s' % dst)
                os.makedirs(dst)


            # FIXME: clean up this mess, we obviously assume existence of
            # certain files
            logger.write('Copying the following files to %s' % dst)

            protein_dir = os.path.join(protein.topdir, protein.workdir,
                                       protein.mol_name)
            ligand_dir = os.path.join(ligand.topdir, ligand.workdir,
                                      ligand.mol_name)

            PROTEIN_PDB_FILE = 'protein.pdb'

            filedir = (
                (protein.mol_file, protein_dir, PROTEIN_PDB_FILE),
                (self.ligand_file, ligand_dir, ''),
                (ligand.frcmod, ligand_dir, ''),
                (const.LIGAND_AC_FILE, ligand_dir, ''),
            )

            for fname, direc, new_fname in filedir:
                filename = os.path.join(direc, fname)

                if not os.access(filename, os.R_OK):
                    continue            # FIXME: e.g. frcmod may not exist
                    #raise errors.SetupError('file %s cannot be read' % filename)

                if new_fname:
                    logger.write('  %s (as %s)' % (filename, new_fname) )
                    shutil.copy(filename, os.path.join(dst, new_fname) )
                else:
                    logger.write('  %s' % filename)
                    shutil.copy(filename, dst)

        except OSError as why:
            raise errors.SetupError(why)

        if PROTEIN_PDB_FILE:
            self.protein_file = PROTEIN_PDB_FILE
        else:
            self.protein_file = protein.mol_file

        # ensure we get the charge also in restarts
        protein.get_charge()
        ligand.get_charge()

        self.charge = protein.charge + ligand.charge

        if abs(self.charge) > const.TINY_CHARGE:
            logger.write('Warning: non-zero complex charge (%f)' % self.charge)

        self.protein = protein
        self.ligand = ligand
        self.frcmod = self.ligand.frcmod

        # FIXME: needed for __enter__ and __exit__ in class Common
        self.dst = dst
        self.topdir = ligand.topdir


    @report
    def create_top(self, boxtype = '', boxlength = 10.0, boxfile = None,
                   align = False, neutralize = False, make_gaff = True,
                   addcmd = '', addcmd2 = '', remove_first = False):
        """Generate an AMBER topology file via leap.

        :param boxtype: rectangular, octahedron or set (set dimensions explicitly)
        :param boxlength: side length of the box
        :param boxfile: name of file containing box dimensions
        :param align: align solute along the principal axes
        :param neutralize: neutralise the system
        :param make_gaff: force GAFF fromat of the ligand
        :param addcmd: inject additional leap commands
        :param remove_first: remove first unit/residue
        :type boxtype: string
        :type boxlength: float
        :type boxfile: string
        :type align: bool
        :type neutralize: bool
        :type make_gaff: bool
        :type addcmd: string
        :type remove_first: bool
        """

        # ensure ligand is in MOL2/GAFF format
        if os.access(const.LIGAND_AC_FILE, os.F_OK):
            mol_file = const.GAFF_MOL2_FILE
            antechamber = utils.check_amber('antechamber')
            utils.run_amber(antechamber,
                            '-i %s -fi ac -o %s -fo mol2 -j 1 -at gaff -pf y' %
                            (const.LIGAND_AC_FILE, mol_file) )
            load_cmd = 'loadmol2 "%s"' % mol_file
        else:
            # antechamber has troubles with dummy atoms
            mol_file = self.ligand_file

            if self.ligand_fmt == 'pdb':
                load_cmd = 'loadpdb "%s"' % mol_file
            elif self.ligand_fmt == 'mol2':
                load_cmd = 'loadmol2 "%s"' % mol_file
            else:
                raise ValueError
                raise errors.SetupError('Leap unsupported input format: %s (only '
                                        'mol2 and pdb)' % self.mol_fmt)


        # FIXME: the "s = combine { l p }" needs to be overwritten in
        #        pmemd/dummy because assumptions is that ligand0 is named s
        leapin = '''%s
source leaprc.gaff
%s
%s
mods = loadAmberParams "%s"
l = %s
p = loadpdb "%s"
s = combine { l p }
%s
''' % (self.ff_cmd, self.solvent_load, addcmd, self.frcmod, load_cmd,
       self.protein_file, addcmd2)


        # FIXME: there can be problems with the ordering of commands, e.g.
        #        when tip4pew is used the frcmod files are only loaded after
        #        reading PDB and MOL2
        leapin += self._amber_top_common(boxtype, boxlength, boxfile, align,
                                         neutralize,
                                         remove_first = remove_first)

        utils.run_leap(self.amber_top, self.amber_crd, 'tleap', leapin)


    @report
    def prot_flex(self, cut_sidechain = 15.0, cut_backbone = 15.0):
        """
        Create a flexibility file for the protein describing how the input
        molecule can be moved by Sire.

        :param cut_sidechain: side chain cutoff
        :type cut_sidechain: float
        :param cut_backbone: backbone cutoff
        :type cut_backbone: float
        :raises: SetupError
        """


        if cut_sidechain < 0.0 or cut_backbone < 0.0:
            raise errors.SetupError('Cutoffs must be positive')


        import Sire.IO

        amber = Sire.IO.Amber()
        molecules, space = amber.readCrdTop(self.sander_crd, self.amber_top)

        moleculeNumbers = molecules.molNums()
        moleculeNumbers.sort()
        moleculeList = []

        for moleculeNumber in moleculeNumbers:
            molecule = molecules.molecule(moleculeNumber).molecule()
            moleculeList.append(molecule)

        ligand = moleculeList[0]
        not_ligand = moleculeList[1:]

        sc_bb_residues = []

        logger.write('Computing flexible protein residues from %s' %
                     self.sander_crd)

        for cut in cut_sidechain, cut_backbone:
            cut_residues = []
            cut2 = cut**2

            for molecule in not_ligand:

                #for residue in molecule.residues():
                nmolresidues = molecule.nResidues()
                for z in range(0,nmolresidues):
                    residue = molecule.residues()[z]
                    # FIXME: a better way to skip unwanted residues would be to
                    # examine amber.zmatrices directly
                    # .value() returns a QtString!
                    if (str(residue.name().value()) not in
                        const.AMBER_PROTEIN_RESIDUES):
                        continue

                    shortest_dist2 = float('inf')

                    #for resat in residue.atoms():
                    nresatoms = residue.nAtoms()
                    for x in range(0,nresatoms):
                        resat = residue.atoms()[x]

                        if (resat.property('mass').value() <
                            const.MAX_HYDROGEN_MASS):
                            continue

                        rescoords = resat.property('coordinates')

                        #for ligat in ligand.atoms():
                        nligatoms = ligand.nAtoms()
                        for y in range(0,nligatoms):
                            ligat = ligand.atoms()[y]

                            if (ligat.property('mass').value() <
                                const.MAX_HYDROGEN_MASS):
                                continue

                            ligcoords = ligat.property('coordinates')
                            dist2 = space.calcDist2(rescoords, ligcoords)

                            if dist2 < shortest_dist2:
                                shortest_dist2 = dist2

                    if shortest_dist2 < cut2:
                        cut_residues.append(residue)

            sc_bb_residues.append(cut_residues)

        lines = ['''# Flexible residues were only selected from the following list of residue names
# %s
# Cut-off for selection of flexible side chains %s Angstroms
# Number of residues with flexible side chains: %s
# Cut-off for selection of flexible backbone: %s Angstroms
# Number of residues with flexible backbone: %s
''' % (', '.join(const.AMBER_PROTEIN_RESIDUES), cut_sidechain,
       len(sc_bb_residues[0]), cut_backbone, len(sc_bb_residues[1])) ]

        htext = ['flexible sidechain', 'flexible backbone']

        for i in 0, 1:
            lines.append("%s\n" % htext[i])
            nums = []

            for residue in sc_bb_residues[i]:
                nums.append(residue.number().value() )

            nums.sort()

            line = ''
            for num in nums:
                if len(line) > 75:
                    lines.append('%s\n' % line)
                    line = ''
                line += ' %4d' % num

            lines.append('%s\n' % line)

        with open(const.PROTEIN_FLEX_FILE, 'w') as output:
            output.write(''.join(lines))



if __name__ == '__main__':
    pass