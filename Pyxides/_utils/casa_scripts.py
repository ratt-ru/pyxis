fixuvw_casa = """msname = '$msname'
rowstep = ${rowstep?100000}
write_uvw = ${write_uvw?False}

# open main MS table, and ANTENNA and FIELD subtable
tb.open(msname+'/ANTENNA');
antpos = tb.getcol("POSITION").transpose()
# this will be a 2-vector for the direction of field 0 in MS

tb.open(msname+'/FIELD');
radec = tb.getcol("PHASE_DIR").transpose()

tb.open(msname,nomodify=not write_uvw)
# indices
ant1,ant2 = tb.getcol("ANTENNA1"),tb.getcol("ANTENNA2")
field = tb.getcol("FIELD_ID")
time = tb.getcol("TIME_CENTROID");
uvw0 = tb.getcol("UVW").transpose();
uvw = uvw0.copy();

import numpy,math

dq,dm = qa,me
nant = antpos.shape[0]

f0 = t0 = None

ant_uvw = antpos.copy();

# make list of ITRF baselines per antenna
ant_bl_itrf = [ dm.baseline('itrf',*[ dq.quantity(x,'m') for x in antpos[i,:]-antpos[0,:]]) for i in range(nant) ]

print "### Printing computed minus stored UVWs every %d rows. Hopefully the delta is small..."%rowstep;
for row,(t,f,a1,a2) in enumerate(zip(time,field,ant1,ant2)):
    if t != t0:
        epoch = dm.epoch("UTC",dq.quantity(t,"s"))
        dm.doframe(epoch)
    if f != f0:
        ra,dec = radec[f][0];
        dir0 = dm.direction('J2000',dq.quantity(ra,"rad"),dq.quantity(dec,"rad"));
        dm.doframe(dir0);
    # recompute all baselines for this timeslot
    if t != t0 or f != f0:
      # convert to J2000 UVWs
      ant_bl_j2000 = [ dm.touvw(x)[1]['value'] for x in ant_bl_itrf ];
      for i,bl in enumerate(ant_bl_j2000):
        ant_uvw[i,:] = bl; 
    t0,f0 = t,f
    uvw[row,:] = ant_uvw[a1,:] - ant_uvw[a2,:];
    if not row%rowstep:
      print "row %d delta-uvw "%row,uvw[row,:] - uvw0[row,:]

if write_uvw:
  print "Writing new UVW column";
  tb.putcol("UVW",uvw.transpose());
""";