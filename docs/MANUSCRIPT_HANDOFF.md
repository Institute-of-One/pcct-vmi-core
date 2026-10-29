# 論文化ハンドオフ（JXST 特集投稿向け）— 2026-10-29 時点

この文書は **ChatGPT / Claude など外部セッションへの引き継ぎ用**に作成した。
実験・結果はすべて完了・コミット済み（`4237528`、tests 96 件全パス）。
残作業は**原稿執筆（Sprint 5）と投稿ゲート**のみ。

## 0. 執筆セッションが最初に読むもの（必順）

1. **`D:\DevGit\AGENTS.md`**（このファイルのある場所の親規則。IORN-013 の教訓:
   外で始めた作業はこの文書を読まずに進んだため失敗した。投稿規則・
   ゲート・絶対禁止事項がここにある）
2. **`D:\DevGit\IoO\docs\IoO_Submission_Runbook.md` §2（体裁要件）と §11（投稿直前チェックリスト）**
   — AGENTS.md §0 により「原稿の作業に入る前に必ず読む」と明記されている
3. **`docs/PROTOCOL_FREEZE.md`**（設計の全部。§12 が実データアーム）
4. **`D:\DevGit\IoO\docs\IORN-016_spec_and_plan.md`**（計画書。§4 仮説、§7 図版計画、
   §11 参考文献アンカー）

## 1. 研究サマリ（1 段落）

PCCT の VMI スタック（40–190 keV、16 レベル）に対し、単画像損失の CNN デノイザ（D1）、
スペクトル整合損失つき（D2）、3D TV（D3）を適用し、(a) NPWE モデル観測者による
検出可能度 d′(keV)、(b) ヨード定量精度、(c) そのトレードオフをシミュレーションで測定し、
公開クルミ PCCT 実データ（Sci Data 2025 / Zenodo 17328375）で外挿検証した。
タイトル案（計画 §1、改題可）: *Denoising the spectral stack: task detectability
and iodine quantitation after AI denoising of photon-counting-detector CT virtual
monoenergetic images — a simulation study with real photon-counting data validation*

## 2. 仮説と判定（計画 §4。凍結済み・変更不可）

| 仮説 | 内容 | 判定 |
|---|---|---|
| H1 | デノイジングで d′ が上がり、最適 keV は低 keV 側へ移動 | 計画 §9 Sprint 2 で測定済み（`results/detectability_spectrum.json` は Raw のみ。D1/D2/D3 付きの d′(keV) は `results/denoised_eval.json` / `denoised_eval_d2.json`）。**判定文は執筆時にこれら JSON から数値を取って明記すること**（現コンテキストの確定値なし。書く前に JSON から取る） |
| H2 | 単画像損失デノイザは d′ を改善する一方ヨード定量を悪化させる | Sprint 3–5 測定済み（`results/denoised_eval.json` の `quantitation` フィールド）。同上 |
| H3 | スペクトル整合損失は定量を回復しつつ d′ 改善を維持 | **棄却（Sprint 6、コミット 99dc997）**。β=3.0 で選別したが 100% 条件で系統的正バイアス、25% で 2 基底残差 5–6 倍悪化。「棄却した仮説も結果として報告する」が凍結 #12 と計画 §12 で明記済み |
| H4 | クルミ実データで同じ向きの効果 | **支持（Sprint 7、コミット 4237528、PROTOCOL_FREEZE §12.8）** |

## 3. 結果ファイルの地図（`results/`。すべて版管理済み）

| ファイル | 内容 | 仮説 |
|---|---|---|
| `detectability_spectrum.json` | Raw のみ、d′(keV)（欠陥径 3/5/8 mm × 線量 100%/25%、n=64）。**ヘッドライン（検証済み）: d′ 最適は全条件で 60 keV。d′max = 3.78/1.92（3 mm）、4.22/2.08（5 mm）、4.68/2.35（8 mm）@100%/25%** | H1 |
| `denoised_eval.json` | D1（単画像損失）。条件ごと per-keV: `d_npwe_raw` vs `d_npwe_denoised`、`signal_attenuation_*`、`quantitation`（ヨードバイアス/SD）、`nps_var_*` | H1/H2 |
| `denoised_eval_d2.json` | D2（スペクトル整合損失、β=3.0 選別）。同上フィールド | H3（棄却の証拠） |
| `tv_eval.json` / `tv_weight_selection.json` | D3（3D TV）の評価と重み選定（S5-3: 0.5σ̂² ルール） | H1–H3 |
| `quantitation_baseline.json` | 定量バイアスのベースライン | H2 |
| `sensitivity_eval.json` | 感受度解析（観測者・条件の頑健性） | 補足 |
| `walnut_eval_summary.json` | **H4 集計（60 スライス平均）。PROTOCOL_FREEZE §12.8 の表と同一** | H4 |
| `walnut_eval_d{0.25,0.125}.json` | H4 スライス個別レコード（VMI RMSE/SSIM per keV、MD bias/SD、NPS 半径 12 ビン） | H4 |
| `walnut_noise_model_d{0.25,0.125}.{npz,json}` | 凍結ノイズモデル＋統計（n0=3.0×10⁴） | H4 |

集計の参考実装: `_tmp/summarize_detectability.py`、`_tmp/summarize_denoised.py`
（実行補助用。コミット不要だが動く）。

## 4. 図版（計画 §7。Figure 確定は未実施 = Sprint 4 保留のまま）

| 図 | 内容 | 生成経路 |
|---|---|---|
| Fig. 1 | パイプライン図 | `examples/pipeline_montage.png` に試作あり。要作り直し（論文品質） |
| Fig. 2 | d′(keV) 曲線 Raw/D1/D2/D3（矢印で最適 keV 移動） | `detectability_spectrum.json` + `denoised_eval*.json` |
| Fig. 3 | 定量誤差の keV 特性 | `denoised_eval*.json` の `quantitation` |
| Fig. 4 | 検出-定量 Pareto 図 | Fig. 2/3 から集計 |
| Fig. 5 | クルミ実データ画像＋MD 誤差棒グラフ | `results/walnut_preview_d0.25.png`（プレビュー）を論文品質に作り直し＋`walnut_eval_summary.json` から棒グラフ。**AGENTS.md 必須の「実データで結果を示す図」はこれ** |
| Fig. 6（任意） | TCIA EID NPS 対比 | 未実施。なければ省く（計画上「任意」） |

**ルール（AGENTS.md §3）**: 図はすべてスクリプト経由で生成し、ビルドに含める。
`build_all.py` に「出荷する成果物を生成するステップがすべて含まれる」ことを
確認してから提出。Figure 確定前に人間が 1 枚ずつ目視確認。

## 5. 再現コマンド（クリーンチェックアウト検証用）

```bash
cd D:\DevGit\pcct-vmi-core
.venv\Scripts\python.exe -m pytest -q            # 96 tests
# データ（data/ は gitignored。取得は docs/DATA.md どおり）
.venv\Scripts\python.exe tools\fetch_reconstructions.py   # Zenodo 17328375、19 GB
# 主要結果の再生成（チャンク実行。コマンド例は各ツールの docstring）
.venv\Scripts\python.exe tools\walnut_noise_model.py --dose 0.25 --merge
.venv\Scripts\python.exe tools\walnut_eval.py --dose 0.25 --merge
.venv\Scripts\python.exe tools\walnut_summary.py
```

## 6. 投稿ゲート（AGENTS.md §3・計画 §9 Sprint 5。すべて未実施）

- [ ] JXST 特集 CFP の再確認（計画 §9: 内部調査は 2026-09-25。投稿直前に募集が生きているか確認）
- [ ] runbook §2（体裁要件）・§11（チェックリスト）の読了
- [ ] JXST 実テンプレートの取得・確認（Guide for Authors の散文ではなく配布ファイルの実体）
- [ ] `submission/jxst/build_submission_docs.py` と `check_template_conformance.py` / `check_references.py` を IORN 既存実装から複製・適合化（AGENTS.md §3 のゲート構成どおり）
- [ ] 参考文献全件の DOI 解決検査（計画 §11 のアンカー 9 件＋本文引用分。推測で DOI を書かない）
- [ ] クリーンチェックアウト（`git archive` → 新規 venv）で図が出る経路を検証
- [ ] 生成物を人間が目視（本文・図 1 枚ずつ・表）
- [ ] v0.1.0 タグ＋Zenodo アーカイブ（Version DOI を論文が引用、CITATION.cff/README バッジは Concept DOI — AGENTS.md §5）
- [ ] 12-31 直前投稿を避ける（計画 §9）。目標: 12 月上旬投稿

## 7. 執筆上の注意（honest findings。隠さず書く）

1. **H3 は棄却**。凍結 #12「陰性結果も報告する」どおり、D2 の測定値を提示して棄却理由を書く。
   タイトルは結果に寄せて改題してよい（計画 §1）
2. **D1w（実データ）には系統バイアスがある**（pulp ROI bias −3 213 mg/cm³ 相当 @25%、
   Raw は ±20 以内）。総誤差では 5–12 倍改善する「バイアス-分散交換」として正直に記述
3. **12.5% 外挿で D1w の VMI-SSIM が 0.318 まで低下**（学習線量域 25–100% を外れる）。
   TV は MAD スケーリングのため 0.641 を維持。外挿の限界として明記
4. **VMI 演算子は提供 DICOM からの回帰で凍結**（`pcctvmi/walnut.py`。R²≥0.9999988）。
   10-20 の「HAP 組み立て公式の再構成検証」は実装消失により再現不能と判明し訂正済み
   （CHANGELOG と PROTOCOL_FREEZE §12.1 に記録）。Methods では回帰凍結の手続きを書く
5. **提供 MD_Pulp_Shell シリーズはデータセット側 drift**（ビンのどの線形写像とも一致しない）。
   参照 MD は公開校正表（WalnutMDTable、cond=166.88）で自前計算 — データセットの
   Data Note あるいは本稿の Limitations で言及すべき事実
6. ノイズ注入は「定常相関ガウス近似」（S12-3）。近似であることは明記済みの条件どおり明記
7. 学習データは水/ヨードファントム（S1 凍結）で、クルミ果肉の分光特性とは異なる。
   デノイザが学ぶのはノイズ統計であることと、材料近似を Limitations に書く

## 8. 引用候補（計画 §11。DOI は解決検査後に確定）

計画 §11 の 9 アンカー（Willemink 2018 Radiology、Flohr & Schmidt 2023、
McCollough 2023、Cester 2022 QIMS、Vrbaski 2023 Med Phys、Zhou 2025 Sci Data、
radiomics Mendeley、自己引用 IORN-002/003/005）に加え、実データ関係では
**クルミデータの Zenodo DOI 10.5281/zenodo.17328375**（版 DOI。Concept DOI は
15738313）と Sci Data 誌 DOI **10.1038/s41597-025-06246-4** を記載する。
