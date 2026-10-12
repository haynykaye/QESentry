-- Optional: add the open / close schedule columns to an existing QESentry database by hand.
-- You normally do NOT need this: the Teacher Portal adds the columns automatically the first time it starts.
-- Run it (once) only if student PCs will be used before any teacher has opened the updated Teacher Portal.
USE qesentry;
ALTER TABLE exams
    ADD COLUMN opens_at  DATETIME NULL,
    ADD COLUMN closes_at DATETIME NULL;
