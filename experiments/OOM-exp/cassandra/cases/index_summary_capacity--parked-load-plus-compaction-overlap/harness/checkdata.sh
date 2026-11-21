#!/usr/bin/env bash
# R10 phase-1 dataset checks (design §2.5 phase 1): per set one Data.db; Summary.db vs ceil(N/128)*1012 (+header);
# Filter.db 16 B; CompressionInfo.db and Data.db sizes; Estimated cardinality from sstablemetadata.
R=/mydata/s4/r10; T=$R/node/tools/bin/sstablemetadata
declare -A N=([Q1]=4000000 [Q2]=4000000 [Q3]=4000000 [Q4]=4000000 [P7]=7000000 [P12]=12000000 [P21]=21000000)
echo "set,n,ndata,data_b,summary_b,summary_expect_b,summary_dev_pct,filter_b,cinfo_b,index_b,est_cardinality,card_dev_pct"
for s in Q1 Q2 Q3 Q4 P7 P12 P21; do d=$R/data/pristine/$s; n=${N[$s]}
  nd=$(ls $d/*-Data.db | wc -l); D=$(stat -c %s $d/*-Data.db); SU=$(stat -c %s $d/*-Summary.db); F=$(stat -c %s $d/*-Filter.db); CI=$(stat -c %s $d/*-CompressionInfo.db); IX=$(stat -c %s $d/*-Index.db)
  E=$(( (n+127)/128*1012 )); card=$($T $d/*-Data.db 2>/dev/null | grep -i 'Estimated cardinality' | grep -oE '[0-9]+' | head -1)
  python3 -c "print('$s,$n,$nd,$D,$SU,$E,%.3f,$F,$CI,$IX,${card:-NA},%s' % ((($SU-$E)/$E)*100, ('%.2f' % ((${card:-0}-$n)/$n*100)) if '${card}' else 'NA'))"
done
