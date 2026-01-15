#!/bin/bash
# Terminal=true
echo "Starting system backup..."
rsync -av --progress ~/Documents ~/Backup/
