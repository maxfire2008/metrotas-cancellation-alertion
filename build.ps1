#!/bin/pwsh
git checkout main
git pull
git add .
git commit -a
docker-compose build
docker tag ghcr.io/maxfire2008/metrotas-cancellation-alertion:latest ghcr.io/maxfire2008/metrotas-cancellation-alertion:$(git describe --tags --always)
docker tag ghcr.io/maxfire2008/metrotas-cancellation-alertion:latest ghcr.io/maxfire2008/metrotas-cancellation-alertion:stable
docker push ghcr.io/maxfire2008/metrotas-cancellation-alertion --all-tags
ssh -t god@192.168.86.22 "cd ~/metrotas-cancellation-alertion && ~/metrotas-cancellation-alertion/reset.sh"