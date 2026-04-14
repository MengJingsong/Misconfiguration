import java

class TargetIfStmt extends IfStmt {
    TargetIfStmt() {
        (
            this.getFile().toString() = "Lists" and
            this.getLocation().getStartLine() = 198
        )
        or (
            this.getFile().toString() = "Preconditions" and
            this.getLocation().getStartLine() = 87
        )
        or (
            this.getFile().toString() = "Preconditions" and
            this.getLocation().getStartLine() = 268
        )
        or (
            this.getFile().toString() = "LongBitFormat" and
            this.getLocation().getStartLine() = 62
        )
        or (
            this.getFile().toString() = "LongBitFormat" and
            this.getLocation().getStartLine() = 66
        )
        or (
            this.getFile().toString() = "FSNamesystem" and
            this.getLocation().getStartLine() = 2776
        )
        or (
            this.getFile().toString() = "FSNamesystem" and
            this.getLocation().getStartLine() = 2789
        )
        or (
            this.getFile().toString() = "FSDirAttrOp" and
            this.getLocation().getStartLine() = 342
        )
        or (
            this.getFile().toString() = "FSDirXAttrOp" and
            this.getLocation().getStartLine() = 404
        )
        or (
            this.getFile().toString() = "FSNamesystem" and
            this.getLocation().getStartLine() = 5382
        )
        or (
            this.getFile().toString() = "JournalSet" and
            this.getLocation().getStartLine() = 416
        )
        or (
            this.getFile().toString() = "NameNode" and
            this.getLocation().getStartLine() = 1431
        )
    }
}

class TargetIfCallable extends Callable {
    TargetIfCallable() {
        (
            this.getFile().toString() = "FSDirAttrOp" and
            this.getName() = "unprotectedSetQuota" and
            this.getLocation().getStartLine() = 325
        )
        or (
            this.getFile().toString() = "FSDirXAttrOp" and
            this.getName() = "setINodeXAttrs" and
            this.getLocation().getStartLine() = 342
        )
        or (
            this.getFile().toString() = "FSNamesystem" and
            this.getName() = "checkFsObjectLimit" and
            this.getLocation().getStartLine() = 5381
        )
        or (
            this.getFile().toString() = "NameNode" and
            this.getName() = "checkAllowFormat" and
            this.getLocation().getStartLine() = 1430
        )
        or (
            this.getFile().toString() = "LongBitFormat" and
            this.getName() = "combine" and
            this.getLocation().getStartLine() = 61
        )
        or (
            this.getFile().toString() = "Preconditions" and
            this.getName() = "checkState" and
            this.getLocation().getStartLine() = 267
        )
        or (
            this.getFile().toString() = "Preconditions" and
            this.getName() = "checkNotNull" and
            this.getLocation().getStartLine() = 85
        )
        or (
            this.getFile().toString() = "Lists" and
            this.getName() = "checkNonnegative" and
            this.getLocation().getStartLine() = 197
        )
        or (
            this.getFile().toString() = "FSNamesystem" and
            this.getName() = "startFileInt" and
            this.getLocation().getStartLine() = 2724
        )
        or (
            this.getFile().toString() = "JournalSet" and
            this.getName() = "mapJournalsAndReportErrors" and
            this.getLocation().getStartLine() = 387
        )
    }
}