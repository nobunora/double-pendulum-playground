---
title: 二重振り子のカオスマップを作って、気になる初期値をそのままシミュレーションできるようにした
tags:
  - Python
  - シミュレーション
  - 可視化
  - カオス
  - Tkinter
private: false
updated_at: '2026-03-27T13:50:45+09:00'
id: 76a3d75ba4fc98dd1402
organization_url_name: null
slide: false
ignorePublish: false
---

# はじめに

二重振り子は、初期条件をほんの少し変えただけで、かなり違う動きを見せることで有名です。

今回は `theta1-theta2` の初期角度平面に対して FTLE（Finite-Time Lyapunov Exponent）を計算し、どの領域が不安定そうかをヒートマップで見られるツールを作りました。さらに、

- FTLE が最大の点
- FTLE が最小の点
- マップ上で任意にクリックした点

を、そのまま二重振り子シミュレータへ渡して動かせるようにしました。

要するに、

1. カオスマップで面白そうな場所を見つける
2. その初期角度で実際に振らせる
3. さらに長さや重さを変えて遊ぶ

という流れができるようになっています。

リポジトリはこちらです。

- GitHub: https://github.com/nobunora/double-pendulum-playground

# 作ったもの

今回追加した主な機能はこんな感じです。

- FTLE ベースの二重振り子カオスマップ表示
- 任意領域だけを再計算するズーム機能
- Max / Min FTLE の角度表示
- Max / Min の角度でシミュレータを開くボタン
- マップ上の任意点をクリックしてシミュレータへ渡す機能
- 二重振り子シミュレータ側でのパラメータ入力 UI
- シミュレータの MP4 出力

# 変数の意味

シミュレータやカオスマップで出てくる変数を、まず図でまとめるとこんな感じです。

![二重振り子の変数図](https://raw.githubusercontent.com/nobunora/double-pendulum-playground/main/docs/images/double_pendulum_variable_guide.svg)

図の見方は次の通りです。

- `theta1`, `theta2`
  - 初期角度です。記事内のカオスマップではこの 2 つを平面上に並べています。
  - この実装では `0 deg` が真下方向です。
- `omega1`, `omega2`
  - 初期角速度です。
  - UI では数値をそのまま入力し、内部では角度の時間変化として使っています。
- `l1`, `l2`
  - 1 本目と 2 本目の棒の長さです。
- `m1`, `m2`
  - 1 つ目と 2 つ目の質点の重さです。
- `g`
  - 重力加速度です。
- `dt`
  - 数値積分の時間刻みです。小さくすると精細になりますが、そのぶん計算時間が増えます。
- `duration`
  - どれだけ長い時間を積分するかです。
- `grid`
  - カオスマップを何分割で計算するかです。大きいほど細かい地図になります。

ざっくり言うと、

- `theta1`, `theta2`, `omega1`, `omega2` は「どういう初期状態で始めるか」
- `m1`, `m2`, `l1`, `l2`, `g` は「どんな物理系か」
- `dt`, `duration`, `grid` は「どれくらい細かく・長く計算するか」

を表しています。

# カオスマップはどう読むのか

ヒートマップの横軸と縦軸は、それぞれ初期角度 `theta1` と `theta2` です。

- 寒色寄りの領域は比較的規則的
- 暖色寄りの領域は初期値に敏感で、よりカオス的

という見方をしています。

FTLE は「近い初期条件同士が、有限時間のあいだにどれくらい離れていくか」を見る指標なので、値が大きいほど「初期値の違いが結果に効きやすい」と解釈できます。

全体像はこんな感じです。

![全体カオスマップ](https://raw.githubusercontent.com/nobunora/double-pendulum-playground/main/docs/images/chaos_heatmap_m1-1_m2-1_l1-1_l2-1_o1-0_o2-0_grid-2880_dur-10_dt-0p02.png)

# 遊び方

## 1. まず全体像を見る

最初は広い範囲でカオスマップを計算して、全体の模様を見ます。

ここでは、

- どこに複雑な縞や島があるか
- どこが比較的なめらかか

を探します。

## 2. 気になるところをズームする

`Select Area` で領域を選ぶと、その範囲だけを再計算できます。

正方形モードをオンにしておけば、拡大比較がしやすいです。面白いのは、拡大しても細かい構造が続いて見えるところです。

ズームすると、こんな感じで細部の模様を追えます。

![ズームしたカオスマップ](https://raw.githubusercontent.com/nobunora/double-pendulum-playground/main/docs/images/chaos_heatmap_m1-1_m2-1_l1-1_l2-1_o1-0_o2-0_grid-1440_dur-20_dt-0p02.png)

## 3. Max / Min をすぐシミュレータで開く

カオスマップには、その時点の計算範囲で

- `FTLE max`
- `FTLE min`

が表示されます。

そこから

- `Open Max Sim`
- `Open Min Sim`

を押すと、その角度で二重振り子シミュレータを起動できます。

これで、

- いちばん敏感そうな点
- 比較的おとなしい点

をすぐに見比べられます。

## 4. 任意の場所も試せる

`Pick Sim Point` を押してヒートマップ上をクリックすると、その座標の `theta1`, `theta2` をそのままシミュレータへ渡せます。

これがかなり楽しくて、

- 島の真ん中
- 境界付近
- 見た目が似ている隣接点

を順番に試すと、挙動の違いがよく分かります。

# シミュレータ側も触りやすくした

シミュレータ側にも入力 UI を追加して、以下をテキストボックスで変えられるようにしました。

- `theta1`
- `theta2`
- `omega1`
- `omega2`
- `m1`
- `m2`
- `l1`
- `l2`
- `g`
- `dt`
- `duration`

`Start` を押すと、その条件で同じウィンドウ内で再計算して再生します。

つまり、

1. カオスマップで気になる点を探す
2. シミュレータで開く
3. そこから長さや重さを変える

という流れでそのまま遊べます。

# サンプル動画

GitHub のファイル画面は大きい動画をうまくプレビューできないことがあるので、記事からは

- 軽量な preview 動画
- フルサイズの元動画
- GitHub 上のソース置き場

へ分けて飛べるようにしてあります。

## 長時間サンプル

![長時間サンプルのサムネイル](https://raw.githubusercontent.com/nobunora/double-pendulum-playground/main/docs/images/video_previews/double_pendulum_t1-112p563_t2-85p5504_o1-0_o2-0_m1-1_m2-1_l1-1_l2-1_dur-200_dt-0p02.png)

- [軽量 preview を開く](https://raw.githubusercontent.com/nobunora/double-pendulum-playground/main/docs/previews/double_pendulum_t1-112p563_t2-85p5504_o1-0_o2-0_m1-1_m2-1_l1-1_l2-1_dur-200_dt-0p02_preview.mp4)
- [フル動画を開く](https://raw.githubusercontent.com/nobunora/double-pendulum-playground/main/docs/double_pendulum_t1-112p563_t2-85p5504_o1-0_o2-0_m1-1_m2-1_l1-1_l2-1_dur-200_dt-0p02.mp4)
- [GitHub 上の元ファイルを見る](https://github.com/nobunora/double-pendulum-playground/blob/main/docs/double_pendulum_t1-112p563_t2-85p5504_o1-0_o2-0_m1-1_m2-1_l1-1_l2-1_dur-200_dt-0p02.mp4)

## カオスが強い別条件

![別条件サンプルのサムネイル](https://raw.githubusercontent.com/nobunora/double-pendulum-playground/main/docs/images/video_previews/double_pendulum_t1-145p565_t2-96p0076_o1-0_o2-0_m1-1_m2-1_l1-1_l2-1_dur-20_dt-0p02.png)

- [軽量 preview を開く](https://raw.githubusercontent.com/nobunora/double-pendulum-playground/main/docs/previews/double_pendulum_t1-145p565_t2-96p0076_o1-0_o2-0_m1-1_m2-1_l1-1_l2-1_dur-20_dt-0p02_preview.mp4)
- [フル動画を開く](https://raw.githubusercontent.com/nobunora/double-pendulum-playground/main/docs/double_pendulum_t1-145p565_t2-96p0076_o1-0_o2-0_m1-1_m2-1_l1-1_l2-1_dur-20_dt-0p02.mp4)
- [GitHub 上の元ファイルを見る](https://github.com/nobunora/double-pendulum-playground/blob/main/docs/double_pendulum_t1-145p565_t2-96p0076_o1-0_o2-0_m1-1_m2-1_l1-1_l2-1_dur-20_dt-0p02.mp4)

## 20秒の見やすいサンプル

![20秒サンプルのサムネイル](https://raw.githubusercontent.com/nobunora/double-pendulum-playground/main/docs/images/video_previews/double_pendulum_t1-148p25_t2-m177p25_o1-0_o2-0_m1-1_m2-1_l1-1_l2-1_dur-20_dt-0p02.png)

- [軽量 preview を開く](https://raw.githubusercontent.com/nobunora/double-pendulum-playground/main/docs/previews/double_pendulum_t1-148p25_t2-m177p25_o1-0_o2-0_m1-1_m2-1_l1-1_l2-1_dur-20_dt-0p02_preview.mp4)
- [フル動画を開く](https://raw.githubusercontent.com/nobunora/double-pendulum-playground/main/docs/double_pendulum_t1-148p25_t2-m177p25_o1-0_o2-0_m1-1_m2-1_l1-1_l2-1_dur-20_dt-0p02.mp4)
- [GitHub 上の元ファイルを見る](https://github.com/nobunora/double-pendulum-playground/blob/main/docs/double_pendulum_t1-148p25_t2-m177p25_o1-0_o2-0_m1-1_m2-1_l1-1_l2-1_dur-20_dt-0p02.mp4)

動画全体を一覧したい場合は、[docs ディレクトリ](https://github.com/nobunora/double-pendulum-playground/tree/main/docs) からまとめてたどれます。

# Pythonコードの見どころ

ここからは、実際の Python コードがどう分かれているかを軽く整理します。

## カオスマップ側のコード

カオスマップ本体は `double_pendulum_chaos_map.py` に入っています。

大きく分けると、役割は次の 4 つです。

- FTLE を計算する部分
  - 各初期角度について「基準軌道」と「少しだけずらした軌道」を同時に追跡して、ずれの成長率を FTLE として出します。
- 計算を並列化する部分
  - `theta1-theta2` 平面を小さなタスクに分けて、複数プロセスで処理します。
- ヒートマップを描画する部分
  - FTLE の値を色に変換して、画像として描きます。
- GUI を制御する部分
  - エリア選択、Max/Min 表示、PNG 保存、シミュレータ起動をまとめています。

読んでいくときは、次の流れで追うと分かりやすいです。

1. `finite_time_lyapunov_batch(...)`
2. `compute_cell_batch(...)`
3. `show_chaos_map(...)`

という順です。

特に `show_chaos_map(...)` は長いですが、

- UI 部品の定義
- 状態管理
- 再描画
- バックグラウンド計算の回収

が一つに入っている、という見方をすると読みやすいです。

## シミュレータ側のコード

二重振り子シミュレータ本体は `double_pendulum.py` に入っています。

こちらは比較的素直で、

- `derivatives(...)`
  - 運動方程式の右辺
- `rk4_step(...)`
  - 1 ステップ進める
- `simulate(...)`
  - 全時間分の軌道を作る
- `animate_pendulum(...)`
  - Tkinter 上で再生する
- `save_simulation_mp4(...)`
  - MP4 として書き出す

という分担になっています。

今回の変更で、`animate_pendulum(...)` の中には

- テキストボックス入力
- `Start` による再計算
- `Save MP4`

も追加しています。

なので、シミュレータ側を読むときは

1. `simulate(...)` で物理計算
2. `animate_pendulum(...)` で GUI
3. `save_simulation_mp4(...)` で出力

と切り分けて見るのがおすすめです。

# 高速化の工夫

今回いちばん効いたのは、「Python で細かい仕事を大量に回す」部分を減らしたことです。

## 1. セルごとの計算をまとめて NumPy で処理する

素朴に書くと、

- 1 セルごとに
- 1 ステップごとに
- Python の for ループで

計算したくなります。

でもそれだと、計算そのものより Python のループ管理が重くなりがちです。

そこでこのコードでは、複数セルをまとめて配列として持ち、

- `sin`
- `cos`
- 加減乗除
- RK4 更新

を NumPy の配列演算で一気に処理しています。

ざっくり言うと、

- 遅い: 「1セルずつ Python で回す」
- 速い: 「まとめて配列で渡して C 実装にやらせる」

という考え方です。

## 2. タスクをまとめて複数プロセスへ投げる

カオスマップ全体はセル数が多いので、1 個ずつ worker に渡すと通信コストが大きくなります。

そこで、

- 複数セルを 1 タスクにまとめる
- それを複数プロセスへ配る

ようにしています。

さらに、

- worker 数
- `cells_per_task`
- 未完了タスク数
- poll 間隔

を自動調整することで、CPU 使用率が落ちにくいようにしています。

## 3. 描画を「大量の図形」から「画像 1 枚」に変えた

これは体感差がかなり大きかった部分です。

最初は Canvas にセルごとの矩形を大量に描いていたので、計算が終わっていても再描画が重く、表示だけ途中で止まったように見えることがありました。

そこで、

- FTLE 配列をまず画像化する
- 画面にはその画像を貼る

方式に変えました。

この変更で、UI の引っかかりがかなり減っています。

## 4. 発散したセルを早めに無効化する

二重振り子では、条件によって数値が極端に大きくなって `NaN` や `inf` に落ちることがあります。

この状態を放置すると、

- 無駄な計算を続ける
- 警告が大量に出る
- 配列全体の扱いが不安定になる

という問題が起きます。

なので、非有限値や異常に大きくなったセルは途中で無効化して、それ以上追いかけないようにしています。

## 5. 再生用フレームも間引く

シミュレータ側では、数値計算の全ステップをそのまま描画しているわけではありません。

軌道自体は細かく計算しつつ、表示用には

- 目標 FPS
- 最低/最高 FPS
- 軌跡の進み具合

を見てフレームを間引いています。

これで、長いシミュレーションでも Tkinter 上で再生しやすくしています。

# 実装で気を付けたこと

## 描画ボトルネックの解消

最初は Canvas 上に大量のセルを直接描いていたので、計算より描画が重くなることがありました。

そこで、ヒートマップを一枚の画像として生成して貼る方式に変えています。これで描画の取り残しがかなり減りました。

## 数値発散への対策

一部条件では状態が大きく発散して `NaN` や `inf` が出るので、非有限値になったセルは無効化して全体が壊れないようにしています。

# 使い方の流れ

ローカルで動かすときは、たとえば以下です。

```powershell
python double_pendulum_chaos_map.py
python double_pendulum.py
```

カオスマップ側で面白い初期値を見つけて、シミュレータ側でその挙動を確かめるのが一番楽しい使い方だと思います。

# まとめ

今回作ったものは、単なる可視化というより

- 地図として探す
- 気になる点を選ぶ
- その場で動きを見る
- 条件を変えて比較する
- 動画で残す

という「遊べる解析ツール」になりました。

二重振り子は、数式として見ても面白いですが、カオスマップから初期値を拾って実際の運動を見ると、かなり直感的に楽しめます。

今後は、代表サンプルの整理や、記事用素材の絞り込み、比較しやすいプリセット追加などもやっていきたいです。

コード全体を見たい場合は、リポジトリ本体からたどるのが一番分かりやすいです。

- GitHub リポジトリ: https://github.com/nobunora/double-pendulum-playground
- カオスマップ本体: https://github.com/nobunora/double-pendulum-playground/blob/main/double_pendulum_chaos_map.py
- 2D シミュレータ本体: https://github.com/nobunora/double-pendulum-playground/blob/main/double_pendulum.py
- 任意角度ピッカー: https://github.com/nobunora/double-pendulum-playground/blob/main/double_pendulum_theta_picker.py

# 付録: FTLE とは何か

ここでは、記事中で何度も出てきた FTLE をもう少し丁寧に書いておきます。

FTLE は `Finite-Time Lyapunov Exponent` の略で、直訳すると「有限時間リアプノフ指数」です。

カオスの話でよく出てくるリアプノフ指数は、

- ほとんど同じ初期条件を 2 つ用意したとき
- 時間がたつにつれて、その差がどれくらいの速さで広がるか

を見る量です。

今回使っている FTLE は、その「無限時間での極限」ではなく、ある有限時間 `T` だけを見たバージョンです。

イメージとしては、

- すごく近い初期条件 A と B を用意する
- 同じ時間だけシミュレーションする
- 最後にどれだけ離れたかを見る

というものです。

式で書くと、典型的には次の形になります。

```math
\lambda_T = \frac{1}{T} \log \frac{\|\delta x(T)\|}{\|\delta x(0)\|}
```

ここで、

- `x(t)` は系の状態
- `\delta x(0)` は最初の小さなずれ
- `\delta x(T)` は時間 `T` 後のずれ
- `\lambda_T` が FTLE

です。

この値が大きいと、

- 近かった 2 本の軌道が短時間で大きく離れる
- つまり初期値に敏感
- より「カオスっぽい」領域

と見なせます。

逆に小さいと、

- 少し条件を変えてもすぐには大きく離れない
- 比較的規則的に見える

という解釈になります。

ただし、FTLE はあくまで「有限時間での局所的な見え方」です。

なので、

- `duration` を変えると値も変わる
- `dt` を粗くしすぎると精度に影響する
- ある時間では規則的に見えても、もっと長時間では違う可能性がある

という点には注意が必要です。

今回のカオスマップでは、`theta1-theta2` 平面の各セルごとに

1. その初期角度で基準軌道を作る
2. ごく小さくずらした軌道も一緒に作る
3. ずれの成長率を積み上げる
4. 最終的な FTLE を色にする

という流れで値を出しています。

要するに FTLE は、

- 「この初期値は、少しずらしただけでどれくらい未来が変わるか」

を地図にしたものだと思うと分かりやすいです。

その意味で、このツールは

- カオスマップで敏感な領域を探す
- その点をすぐシミュレータで再生する

という流れがかなり相性良くできています。
