# IoO publication gate

規約正本はIoO_Publication_Policy.md。既存の投稿・校正検査に追加するもので、置換しない。

## 新規・改訂論文への導入

1. 対象研究に本ディレクトリをpublication/として配備する。規約はIoO正本とバイト一致するか更新時に確認。独自に規約を弱めない。実装をフォークせずIoO側のスクリプトを呼ぶ構成も可。
2. publication.template.jsonを研究ルートのpublication.jsonへコピーして、原稿・規約・全提出物を明示する。project_rootは設定ファイルからの相対位置。レビューや個人情報は公開許可のないリポジトリへpushしない。
3. 原稿生成後に `python publication/publication_gate.py publication.json --snapshot`。snapshotとpolicy_sha256（files内）を依頼に添える。
4. REVIEW_PROMPT.mdを各AIへ渡す。実際のレビューをreview.template.jsonの形式で各別ファイルへ記録。ChatGPTがローカルを読めない場合、承認済みの資料と規約を添付し、照合可能な応答記録を保存する。自動接続済みとは扱わない。
5. 指摘を解消し、修正版で3者レビューを取得。著者の明示承認後のみhuman.template.jsonを記入する。review_sha256は実際の3記録をSHA-256で計算。承認依頼・応答の所在をapproval_evidenceへ記録。
6. `python publication/publication_gate.py publication.json` が0で終了してから既存の投稿直前チェックを完了する。WARNが残る場合、各AIと著者の理由付き処置が必須。

既存Python投稿ゲートには以下を組み込み、例外を握り潰さない。

```python
subprocess.run([sys.executable, str(IOO / 'publication/publication_gate.py'),
                str(REPO / 'publication.json')], check=True)
```

## GitHub

同梱ワークフローはゲートの回帰テストとIoO内publication/entries/*.jsonを実行する。entriesのproject_rootは設定ファイルの位置から解決される。外部Dドライブを指す設定はGitHubでは使用不可。研究リポジトリ側で同じ検査を組み込み、設定と承認済み資料がrunnerから参照できるようにする。非公開資料は公開CIへ送らない。

GitHub管理者がpublication-checkをRequired status checkに指定し、対象ブランチを保護する。ファイル作成だけではサーバー側の強制は有効にならない。登録0件は論文合格ではなくINFRASTRUCTURE_ONLYと表示する。

## 検査と記録

`python -m unittest discover -s publication -v`

否定的な締めの警告、承認なし、古いレビュー、未解決、版変更、設定変更、欠落ファイルを注入して検証する。これは合成テストであり論文・臨床検証ではない。独立コードレビューは既存SharedTools/AI-Checkを使用し、設定・結果への参照を.ai-checkに保存する。規約が強制できるのは接続済みの経路のみ。全既存研究への遡及導入は別の配備作業。
