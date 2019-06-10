#!/usr/bin/env python
# -*- coding: utf-8 -*-
#  thirdorder, help compute anharmonic IFCs from minimal sets of displacements
#  Copyright (C) 2012-2014 Wu Li <wu.li.phys2011@gmail.com>
#  Copyright (C) 2012-2014 Jesús Carrete Montaña <jcarrete@gmail.com>
#  Copyright (C) 2012-2014 Natalio Mingo Bisquert <natalio.mingo@cea.fr>
#  Copyright (C) 2014      Antti J. Karttunen <antti.j.karttunen@iki.fi>
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

# this program is modified version of thirdorder_vasp.py to interface hdnnpy to shengBTE

import os.path
import glob
try:
    from lxml import etree as ElementTree
    xmllib="lxml.etree"
except ImportError:
    try:
        import xml.etree.cElementTree as ElementTree
        xmllib="cElementTree"
    except ImportError:
        import xml.etree.ElementTree as ElementTree
        xmllib="ElementTree"
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
try:
    import hashlib
    hashes=True
except ImportError:
    hashes=False

import thirdorder_core
from thirdorder_common import *


def read_POSCAR(directory):
    """
    Return all the relevant information contained in a POSCAR file.
    """
    with dir_context(directory):
        nruter=dict()
        nruter["lattvec"]=np.empty((3,3))
        f=open("POSCAR","r")
        firstline=f.next()
        factor=.1*float(f.next().strip())
        for i in xrange(3):
            nruter["lattvec"][:,i]=[float(j) for j in f.next().split()]
        nruter["lattvec"]*=factor
        line=f.next()
        fields=f.next().split()
        old=False
        try:
            int(fields[0])
        except ValueError:
            old=True
        if old:
            nruter["elements"]=firstline.split()
            nruter["numbers"]=np.array([int(i) for i in line.split()])
            typeline="".join(fields)
        else:
            nruter["elements"]=line.split()
            nruter["numbers"]=np.array([int(i) for i in fields],
                                       dtype=np.intc)
            typeline=f.next()
        natoms=nruter["numbers"].sum()
        nruter["positions"]=np.empty((3,natoms))
        for i in xrange(natoms):
            nruter["positions"][:,i]=[float(j) for j in f.next().split()]
        f.close()
    nruter["types"]=[]
    for i in xrange(len(nruter["numbers"])):
        nruter["types"]+=[i]*nruter["numbers"][i]
    if typeline[0]=="C":
        nruter["positions"]=sp.linalg.solve(nruter["lattvec"],
                                               nruter["positions"]*factor)
    return nruter


def write_POSCAR(poscar,filename):
    """
    Write the contents of poscar to filename.
    """
    global hashes
    f=StringIO.StringIO()
    f.write("1.0\n")
    for i in xrange(3):
        f.write("{0[0]:>20.15f} {0[1]:>20.15f} {0[2]:>20.15f}\n".format(
            (poscar["lattvec"][:,i]*10.).tolist()))
    f.write("{0}\n".format(" ".join(poscar["elements"])))
    f.write("{0}\n".format(" ".join([str(i) for i in poscar["numbers"]])))
    f.write("Direct\n")
    for i in xrange(poscar["positions"].shape[1]):
        f.write("{0[0]:>20.15f} {0[1]:>20.15f} {0[2]:>20.15f}\n".format(
            poscar["positions"][:,i].tolist()))
    if hashes:
        header=hashlib.sha1(f.getvalue()).hexdigest()
    else:
        header=filename
    with open(filename,"w") as finalf:
        finalf.write("{0}\n".format(header))
        finalf.write(f.getvalue())
    f.close()


def normalize_SPOSCAR(sposcar):
    """
    Rearrange sposcar, as generated by gen_SPOSCAR, so that it is in
    valid VASP order, and return the result.
    """
    nruter=copy.deepcopy(sposcar)
    # Order used internally (from most to least significant):
    # k,j,i,iat For VASP, iat must be the most significant index,
    # i.e., atoms of the same element must go together.
    indices=np.array(xrange(nruter["positions"].shape[1])).reshape(
        (sposcar["nc"],sposcar["nb"],sposcar["na"],-1))
    indices=np.rollaxis(indices,3,0).flatten().tolist()
    nruter["positions"]=nruter["positions"][:,indices]
    nruter["types"].sort()
    return nruter


#change the read_force to read forces from prediction.nnp
def read_forces():
    '''
    parse prediction results from hdnnpy
    default output npz name: prediction_result.npz
    here I assume prediction_result.npz contain
    energy and force data for all displacement required by phonopy
    with the same ordering in disp.yaml
    '''

    force_set=[]
    prdata=np.load('prediction_result.npz')
    keys=prdata.files
    print(keys)

    #all force data have same key in default hdnnpy setting.
    #thus the actual data number is counted by len(force_set[0])

    for ik in keys:
        if(ik.find('force') >0):
            print('tag to store:'+str(ik))
            force_data=prdata[ik]
            force_set.append(force_data)

    print("size of hdnnpy data:"+str(len(force_set[0])))
    return force_set



def build_unpermutation(sposcar):
    """
    Return a list of integers mapping the atoms in the normalized
    version of sposcar to their original indices.
    """
    indices=np.array(xrange(sposcar["positions"].shape[1])).reshape(
        (sposcar["nc"],sposcar["nb"],sposcar["na"],-1))
    indices=np.rollaxis(indices,3,0).flatten()
    return indices.argsort().tolist()


if __name__=="__main__":
    if len(sys.argv)!=6 or sys.argv[1] not in ("sow","reap"):
        sys.exit("Usage: {0} sow|reap na nb nc cutoff[nm/-integer]".format(sys.argv[0]))
    action=sys.argv[1]
    na,nb,nc=[int(i) for i in sys.argv[2:5]]
    if min(na,nb,nc)<1:
        sys.exit("Error: na, nb and nc must be positive integers")
    if sys.argv[5][0]=="-":
        try:
            nneigh=-int(sys.argv[5])
        except ValueError:
            sys.exit("Error: invalid cutoff")
        if nneigh==0:
            sys.exit("Error: invalid cutoff")
    else:
        nneigh=None
        try:
            frange=float(sys.argv[5])
        except ValueError:
            sys.exit("Error: invalid cutoff")
        if frange==0.:
            sys.exit("Error: invalid cutoff")
    print "Reading POSCAR"
    poscar=read_POSCAR(".")
    natoms=len(poscar["types"])
    print "Analyzing the symmetries"
    symops=thirdorder_core.SymmetryOperations(
        poscar["lattvec"],poscar["types"],
        poscar["positions"].T,SYMPREC)
    print "- Symmetry group {0} detected".format(symops.symbol)
    print "- {0} symmetry operations".format(symops.translations.shape[0])
    print "Creating the supercell"
    sposcar=gen_SPOSCAR(poscar,na,nb,nc)
    ntot=natoms*na*nb*nc
    print "Computing all distances in the supercell"
    dmin,nequi,shifts=calc_dists(sposcar)
    if nneigh!=None:
        frange=calc_frange(poscar,sposcar,nneigh,dmin)
        print "- Automatic cutoff: {0} nm".format(frange)
    else:
        print "- User-defined cutoff: {0} nm".format(frange)
    print "Looking for an irreducible set of third-order IFCs"
    wedge=thirdorder_core.Wedge(poscar,sposcar,symops,dmin,
                                nequi,shifts,frange)
    print "- {0} triplet equivalence classes found".format(wedge.nlist)
    list4=wedge.build_list4()
    nirred=len(list4)
    nruns=4*nirred
    print "- {0} DFT runs are needed".format(nruns)
    if action=="sow":
        print sowblock
        print "Writing undisplaced coordinates to 3RD.SPOSCAR"
        write_POSCAR(normalize_SPOSCAR(sposcar),"3RD.SPOSCAR")
        width=len(str(4*(len(list4)+1)))
        namepattern="3RD.POSCAR.{{0:0{0}d}}".format(width)
        print "Writing displaced coordinates to 3RD.POSCAR.*"
        for i,e in enumerate(list4):
            for n in xrange(4):
                isign=(-1)**(n//2)
                jsign=-(-1)**(n%2)
                # Start numbering the files at 1 for aesthetic
                # reasons.
                number=nirred*n+i+1
                dsposcar=normalize_SPOSCAR(
                    move_two_atoms(sposcar,
                                   e[1],e[3],isign*H,
                                   e[0],e[2],jsign*H))
                filename=namepattern.format(number)
                write_POSCAR(dsposcar,filename)
    else:
        print reapblock
        #print "XML ElementTree implementation: {0}".format(xmllib)
        #print "Waiting for a list of vasprun.xml files on stdin"
        #filelist=[]
        #for l in sys.stdin:
        #    s=l.strip()
        #    if len(s)==0:
        #        continue
        #    filelist.append(s)
        #nfiles=len(filelist)
        #print "- {0} filenames read".format(nfiles)
        #if nfiles!=nruns:
        #    sys.exit("Error: {0} filenames were expected".
        #             format(nruns))
        #for i in filelist:
        #    if not os.path.isfile(i):
        #        sys.exit("Error: {0} is not a regular file".
        #                 format(i))
        #print "Reading the forces"
        p=build_unpermutation(sposcar)
        forces=[]
        hdnnpy_force=read_forces()
        for i in range(nruns):
            forces.append(hdnnpy_force[0][i].reshape(-1, 3)[p,:])
            print "- {0} read successfully".format(i)
            res=forces[-1].mean(axis=0)
            print "- \t Average force:"
            print "- \t {0} eV/(A * atom)".format(res)
        print "Computing an irreducible set of anharmonic force constants"
        phipart=np.zeros((3,nirred,ntot))
        for i,e in enumerate(list4):
            for n in xrange(4):
                isign=(-1)**(n//2)
                jsign=-(-1)**(n%2)
                number=nirred*n+i
                phipart[:,i,:]-=isign*jsign*forces[number].T
        phipart/=(400.*H*H)
        print "Reconstructing the full array"
        phifull=thirdorder_core.reconstruct_ifcs(phipart,wedge,list4,poscar,sposcar)
        print "Writing the constants to FORCE_CONSTANTS_3RD"
        write_ifcs(phifull,poscar,sposcar,dmin,nequi,shifts,frange,"FORCE_CONSTANTS_3RD")
    print doneblock