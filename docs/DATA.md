# 実データの所在と再取得手順（DICOM・生データは再配布しない）

このリポジトリには患者データも生データもコミットしない。
公開データは各自が以下の手順で取得し、`data/`（gitignore 済み）に置く。

## 1. Walnut cone-beam PCD-CT（Zenodo、CC BY 4.0）

- 出典: E. Zhou et al., *Scientific Data* 2025（cone-beam photon-counting CT
  dataset for spectral image reconstruction and deep learning）。
- レコード（リダイレクト先が最新版）:
  - 校正表: https://doi.org/10.5281/zenodo.15738313 （CalibrationTable.zip、62.5 MB）
  - 再構成例: 同レコードの Reconstructions.zip（19.0 GB、Walnut 1 のフルビュー再構成＋材料分解例）
  - 生投影: Walnut_1.zip ほか（Sprint 4 オプション (a) 用。デフォルトは未使用）
- 内訳（2026-10-09 に Zenodo API で確認）:
  - CalibrationTable.zip 62.5 MB / Walnut_1.zip 17.9 GB / CalibrationPhantomData.zip 9.2 GB
    / Reconstructions.zip 19.0 GB
- 取得: `curl -L -o data/walnut/CalibrationTable.zip https://zenodo.org/records/15738313/files/CalibrationTable.zip?download=1`
- ライセンス: CC BY 4.0。論文・リポジトリに出典と DOI を明記する。

## 2. TCIA LIDC-IDRI（EID 実臨床 CT、CC BY 3.0）

- 出典: https://doi.org/10.7937/K9/TCIA.2015.LO9QL9SX
- 用途: 凍結 S-10 どおり 50 例の均一領域 NPS（EID 対比のみ。アノテーション不使用）
- 取得: TCIA NBIA Data Retriever または API。Series Instance UID を
  `data/tcia/PROVENANCE.json` に記録する（DICOM はコミットしない）。

## 3. Charité / NAEOTOM Alpha（外部検証オプション）

- 2026-11-15 到着・条件合意が前提。届いた時点でこのファイルに所在・
  利用条件・PROVENANCE を追記する。査読者候補として関係者を使わない。
