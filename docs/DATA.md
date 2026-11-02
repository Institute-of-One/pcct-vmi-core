# Where the real data comes from, and how to fetch it again

No patient data and no raw data is committed to this repository, and none is
redistributed by it. The public datasets below are fetched by whoever wants to rerun the
work and placed under `data/`, which `.gitignore` excludes.

The manuscript's data-availability statement points here, so this file is in English
first; the original Japanese follows unchanged.

## 1. Walnut cone-beam PCD-CT (Zenodo, CC BY 4.0)

This is the real-data arm: the reconstructions behind Figure 5 and the walnut stress
test.

- **Source:** E. Zhou et al., *Scientific Data* 2025, a cone-beam photon-counting CT
  dataset for spectral image reconstruction and deep learning,
  <https://doi.org/10.1038/s41597-025-06246-4>. The authors' reconstruction code
  (MATLAB, MIT) is at <https://github.com/zezisme/WalnutPCCTReconCodes>.
- **Record (revised 2026-10-20):** the file URLs of the older record `15738313` now
  return 404. Fetch from the current record it redirects to,
  **<https://doi.org/10.5281/zenodo.17328375>**:
  - `CalibrationTable.zip` (62.5 MB) - the calibration table;
  - `Reconstructions.zip` (19.0 GB) - full-view reconstructions of walnut 1 and the
    material-decomposition examples. This is the one the figures need;
  - `Walnut_1.zip` and the other raw-projection archives are not used by default.
- **Fetching:**

  ```bash
  curl -L -o data/walnut/CalibrationTable.zip \
    "https://zenodo.org/records/17328375/files/CalibrationTable.zip?download=1"
  python tools/fetch_reconstructions.py
  ```

  A single connection runs at about 1.8 MB/s, so the 19 GB archive is fetched by
  `tools/fetch_reconstructions.py`, which uses ranged parallel requests and can resume.
- **Checksums** (MD5, compared against the Zenodo API on 2026-10-20):
  `CalibrationTable.zip` = `0273d689b2ca4233e5d1a653af8943f4`,
  `Reconstructions.zip` = `88ef5d61c638f68fba484fc77d0d80d3`. What was fetched and how it
  verified is recorded in `data/walnut/PROVENANCE.json`, which is also not committed.
- **Licence:** CC BY 4.0. The source and its DOI are cited in the manuscript and in this
  repository.

## 2. TCIA LIDC-IDRI (energy-integrating clinical CT, CC BY 3.0)

- **Source:** <https://doi.org/10.7937/K9/TCIA.2015.LO9QL9SX>
- **Use:** the uniform-region noise power spectrum of 50 cases, as frozen in S-10, for
  the energy-integrating comparison only. The annotations are not used.
- **Fetching:** the TCIA NBIA Data Retriever or the TCIA API. Record the series instance
  UIDs in `data/tcia/PROVENANCE.json`; no DICOM is committed.

---

# 実データの所在と再取得手順（DICOM・生データは再配布しない）

このリポジトリには患者データも生データもコミットしない。
公開データは各自が以下の手順で取得し、`data/`（gitignore 済み）に置く。

## 1. Walnut cone-beam PCD-CT（Zenodo、CC BY 4.0）

- 出典: E. Zhou et al., *Scientific Data* 2025（cone-beam photon-counting CT
  dataset for spectral image reconstruction and deep learning）。
  DOI: 10.1038/s41597-025-06246-4。再構成コード（MATLAB）:
  https://github.com/zezisme/WalnutPCCTReconCodes （MIT）。
- **レコード（2026-10-20 改訂）:** 旧レコード `15738313` のファイル URL は
  404 を返すようになった。リダイレクト先の最新版レコード
  **https://doi.org/10.5281/zenodo.17328375** で取得する。
  - 校正表: 同レコードの CalibrationTable.zip（62.5 MB）
  - 再構成例: Reconstructions.zip（19.0 GB、Walnut 1 のフルビュー再構成＋材料分解例）
  - 生投影: Walnut_1.zip ほか（既定では未使用）
- 取得: `curl -L -o data/walnut/CalibrationTable.zip "https://zenodo.org/records/17328375/files/CalibrationTable.zip?download=1"`
  Reconstructions.zip（19 GB）は単一接続 ~1.8 MB/s のため
  `tools/fetch_reconstructions.py`（レンジ並列・再開可能）を使う。
- MD5（Zenodo API 値と照合済み、2026-10-20）:
  CalibrationTable.zip = `0273d689b2ca4233e5d1a653af8943f4`、
  Reconstructions.zip = `88ef5d61c638f68fba484fc77d0d80d3`。
  取得済みファイルの所在・検証結果は `data/walnut/PROVENANCE.json`。
- ライセンス: CC BY 4.0。論文・リポジトリに出典と DOI を明記する。

## 2. TCIA LIDC-IDRI（EID 実臨床 CT、CC BY 3.0）

- 出典: https://doi.org/10.7937/K9/TCIA.2015.LO9QL9SX
- 用途: 凍結 S-10 どおり 50 例の均一領域 NPS（EID 対比のみ。アノテーション不使用）
- 取得: TCIA NBIA Data Retriever または API。Series Instance UID を
  `data/tcia/PROVENANCE.json` に記録する（DICOM はコミットしない）。
