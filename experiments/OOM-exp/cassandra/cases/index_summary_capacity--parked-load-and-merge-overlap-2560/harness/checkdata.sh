#!/usr/bin/env bash
# R18 phase-1 checks of Q7 (design §2.5 phase 1; R10's checkdata.sh with the Q7 sets): one Data.db; Summary.db vs
# ceil(N/128)*1012 (+2,032 header expected); Filter.db 16 B; CompressionInfo.db; Data.db; Estimated cardinality.
R=/mydata/s4/r18; T=/mydata/s4/cassandra-base/tools/bin/sstablemetadata
echo "set,n,ndata,data_b,summary_b,summary_expect_b,summary_dev_pct,filter_b,cinfo_b,index_b,est_cardinality,card_dev_pct"
for s in Q7a Q7b Q7c Q7d; do d=$R/data/pristine/$s; n=7000000
  nd=$(ls $d/*-Data.db | wc -l); D=$(stat -c %s $d/*-Data.db); SU=$(stat -c %s $d/*-Summary.db); F=$(stat -c %s $d/*-Filter.db); CI=$(stat -c %s $d/*-CompressionInfo.db); IX=$(stat -c %s $d/*-Index.db)
  E=$(( (n+127)/128*1012 )); card=$($T $d/*-Data.db 2>/dev/null | grep -i 'Estimated cardinality' | grep -oE '[0-9]+' | head -1)
  python3 -c "print('$s,$n,$nd,$D,$SU,$E,%.3f,$F,$CI,$IX,${card:-NA},%s' % ((($SU-$E)/$E)*100, ('%.2f' % ((${card:-0}-$n)/$n*100)) if '${card}' else 'NA'))"
done
