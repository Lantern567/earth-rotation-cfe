# Chasing wind and sun leaves hourly clean power gaps for data centres serving interactive workloads

Official code and data repository for **“Chasing wind and sun leaves hourly clean power gaps for data centres serving interactive workloads”**.

The Nature Communications revision package is in [`paper_release/nc_revision_20261005/`](paper_release/nc_revision_20261005/). It includes analysis and plotting code, derived hourly inputs, complete result tables, frozen figures, source data and exact reconstruction commands.

## Reproduce the paper

The **28 October 2026 update** is distributed on the same [fixed NC revision release](https://github.com/Lantern567/earth-rotation-cfe/releases/tag/v1.2.0-nc-revision). Download `NC_Revision_Reproducibility_Package_20261028_v3.zip` for the complete current scientific archive, then extract `NC_Revision_Update_20261028.zip` into the same directory. Start with `Reproducibility_Package/README_PUBLIC_UPDATE_20261028.md`. The release tag remains at commit `b50e3685ecdb44a7feb44ccdcea39f41561d0abc`; the automatically generated Git source archive retains that October 5 snapshot. The release update includes Figure S10 source data and scripts, receiver eligibility evidence and sensitivity, coordinate-labelled maps and their drawing scripts, and the eight restored hourly inputs. The asset checksums are in `NC_Release_Update_20261028_SHA256SUMS.txt`.

1. Use the NC revision tag `v1.2.0-nc-revision` and follow the [NC package README](paper_release/nc_revision_20261005/README.md).
2. Restore the large hourly certificate file from the [complete NC release](https://github.com/Lantern567/earth-rotation-cfe/releases/tag/v1.2.0-nc-revision) before checking all supplied hourly certificates. The README provides its location and SHA-256.
3. Trace each result with the [NC reproducibility index](paper_release/nc_revision_20261005/REPRODUCIBILITY_INDEX.md) and use the component requirements and commands from the package directory.

## Repository scope

This public repository is intentionally limited to the manuscript and its reproducibility package. The broader development workspace, unrelated projects, caches and exploratory outputs are not included. Large third-party raw datasets that cannot be redistributed remain available from the original providers listed in the manuscript; redistributable figure source data and derived results are included in `paper_release/`.

## Submission version

The NC revision is identified by `v1.2.0-nc-revision`. The earlier `v1.1.0-submission` tag and its [original release layout](paper_release/README.md) remain available as an earlier submission snapshot. The earlier tag does not identify the reviewed or revised NC manuscript.

## Licence

Source code is released under the MIT License; see [`LICENSE`](LICENSE). Newly generated derived data are released under CC BY 4.0 subject to the qualifications in [`DATA_LICENSE.md`](DATA_LICENSE.md). Third-party inputs retain their original licences and terms.
