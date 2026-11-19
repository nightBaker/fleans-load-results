#!/usr/bin/env bash
# build.sh ROOT TAG PROJECTS... — same as tests/load/build-images.sh minus Citus (amd64: citusdata/citus image).
set -euo pipefail
ROOT="$1"; TAG="$2"; shift 2
WORK="$(mktemp -d)"
for spec in "$@"; do
  project="${spec%%=*}"; image="${spec##*=}"
  dotnet publish "$ROOT/src/Fleans/$project/$project.csproj" -c Release -o "$WORK/$project/app" --nologo -v q
  cat > "$WORK/$project/Dockerfile" <<DF
FROM mcr.microsoft.com/dotnet/aspnet:11.0
WORKDIR /app
COPY app/ .
ENV ASPNETCORE_HTTP_PORTS=8080
ENTRYPOINT ["dotnet", "$project.dll"]
DF
  docker build -q -t "$image:$TAG" "$WORK/$project"
done
rm -rf "$WORK"
