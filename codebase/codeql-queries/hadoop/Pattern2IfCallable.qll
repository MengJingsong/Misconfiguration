import java

class Pattern2IfCallable extends Callable {
    Pattern2IfCallable() {
        isPattern2Location(this.getFile().getRelativePath(), this.getLocation().getStartLine())
    }
}

predicate isPattern2Location(string path, int startLine) {
  (
    path = "hadoop-tools/hadoop-gridmix/src/main/java/org/apache/hadoop/mapred/gridmix/GridmixJob.java" and startLine = 266
  ) or (
    path = "hadoop-cloud-storage-project/hadoop-cos/src/main/java/org/apache/hadoop/fs/cosn/BufferPool.java" and startLine = 165
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/util/LongBitFormat.java" and startLine = 61
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/PeerCache.java" and startLine = 98
  ) or (
    path = "hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/FileOutputFormat.java" and startLine = 111
  ) or (
    path = "hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/JobResourceUploader.java" and startLine = 587
  ) or (
    path = "hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/Task.java" and startLine = 820
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/protocol/datatransfer/PacketReceiver.java" and startLine = 122
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/snapshot/SnapshotManager.java" and startLine = 142
  ) or (
    path = "hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-nativetask/src/main/java/org/apache/hadoop/mapred/nativetask/NativeMapOutputCollectorDelegator.java" and startLine = 74
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/checker/StorageLocationChecker.java" and startLine = 90
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/checker/StorageLocationChecker.java" and startLine = 151
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/checker/DatasetVolumeChecker.java" and startLine = 116
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/BlockManager.java" and startLine = 615
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/BlockManager.java" and startLine = 627
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/BlockManager.java" and startLine = 645
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/ShortCircuitRegistry.java" and startLine = 157
  ) or (
    path = "hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/lib/partition/TotalOrderPartitioner.java" and startLine = 76
  ) or (
    path = "hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/split/SplitMetaInfoReader.java" and startLine = 44
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSNamesystem.java" and startLine = 866
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSNamesystem.java" and startLine = 2724
  ) or (
    path = "hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/MapTask.java" and startLine = 972
  ) or (
    path = "hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/JobSubmitter.java" and startLine = 138
  ) or (
    path = "hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/lib/output/FileOutputCommitter.java" and startLine = 135
  ) or (
    path = "hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/counters/Limits.java" and startLine = 95
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/balancer/Balancer.java" and startLine = 860
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataNode.java" and startLine = 1880
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/FSDirXAttrOp.java" and startLine = 342
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/namenode/JournalSet.java" and startLine = 387
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DataStorage.java" and startLine = 348
  ) or (
    path = "hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsDatasetCache.java" and startLine = 152
  ) or (
    path = "hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/util/Lists.java" and startLine = 197
  )
}