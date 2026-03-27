---
title: 二重振り子のカオスマップを作って、気になる初期値をそのままシミュレーションできるようにした
tags:
  - Python
  - シミュレーション
  - 可視化
  - カオス
  - Tkinter
private: false
updated_at: '2026-03-27T14:37:15+09:00'
id: 76a3d75ba4fc98dd1402
organization_url_name: null
slide: false
ignorePublish: false
---

# 1. どうしてこれを作ったか

二重振り子は、初期条件をほんの少し変えただけで、かなり違う動きを見せることで有名です。

せっかくなので、どの初期角度で挙動が変わりやすいのかを地図みたいに見たくなり、`theta1-theta2` の初期角度平面に対して FTLE（Finite-Time Lyapunov Exponent）を計算するツールを作りました。さらに、

- FTLE が最大の点
- FTLE が最小の点
- マップ上で任意にクリックした点

を、そのまま二重振り子シミュレータへ渡して動かせるようにしました。

やりたかったのは、

1. カオスマップで面白そうな場所を見つける
2. その初期角度で実際に振らせる
3. さらに長さや重さを変えて遊ぶ

という流れです。

リポジトリはこちらです。

- GitHub: https://github.com/nobunora/double-pendulum-playground

# 2. 何を作ったか

今回入れた主な機能はこんな感じです。

- FTLE ベースの二重振り子カオスマップ表示
- 任意領域だけを再計算するズーム機能
- Max / Min FTLE の角度表示
- Max / Min の角度でシミュレータを開くボタン
- マップ上の任意点をクリックしてシミュレータへ渡す機能
- 二重振り子シミュレータ側でのパラメータ入力 UI
- シミュレータの MP4 出力

# 3. 変数

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

まとめると、

- `theta1`, `theta2`, `omega1`, `omega2` は「どういう初期状態で始めるか」
- `m1`, `m2`, `l1`, `l2`, `g` は「どんな物理系か」
- `dt`, `duration`, `grid` は「どれくらい細かく・長く計算するか」

を表しています。

# 4. カオスマップの見方

ヒートマップの横軸と縦軸は、それぞれ初期角度 `theta1` と `theta2` です。

- 寒色寄りの領域は比較的規則的
- 暖色寄りの領域は初期値に敏感で、よりカオス的

という見方です。

FTLE は「近い初期条件同士が、有限時間のあいだにどれくらい離れていくか」を見る指標なので、値が大きいほど初期値の違いが結果に効きやすいと解釈できます。

全体像はこんな感じです。

![全体カオスマップ](https://raw.githubusercontent.com/nobunora/double-pendulum-playground/main/docs/images/chaos_heatmap_m1-1_m2-1_l1-1_l2-1_o1-0_o2-0_grid-2880_dur-10_dt-0p02.png)

# 5. 遊び方

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

をすぐ見比べられます。

## 4. 任意の場所も試せる

`Pick Sim Point` を押してヒートマップ上をクリックすると、その座標の `theta1`, `theta2` をそのままシミュレータへ渡せます。

この機能を入れると、

- 島の真ん中
- 境界付近
- 見た目が似ている隣接点

を順番に試すと、挙動の違いがよく分かります。

# 6. シミュレータ側

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

# 7. サンプル動画

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

# 8. 触っていて面白いところ

このツール、作ってみて一番面白いのは「地図で見た模様」と「実際の動き」がちゃんとつながるところでした。

例えば、

- 色の変わり目に近い場所を何点か試す
- 見た目が似ている隣の点を比べる
- Max と Min を続けて再生する

だけでも、かなり違う動きになります。

特に、マップ上では近いのに動かしてみると全然印象が違う、という場所がいくつもあります。このあたりは、二重振り子らしい面白さがそのまま見える感じでした。

あと、シミュレータ側で

- 長さを少し変える
- 重さを変える
- `duration` を伸ばす

みたいなことをやると、同じ初期角度でも見え方が変わるので、つい何本も動画を保存して見比べたくなります。

# 9. 実行方法

ローカルで動かすときは、たとえば以下です。

```powershell
python double_pendulum_chaos_map.py
python double_pendulum.py
```

カオスマップ側で気になる初期値を見つけて、シミュレータ側でその挙動を確かめる、という使い方が基本です。

# 10. まとめ

今回作ったものは、単なる可視化というより

- 地図として探す
- 気になる点を選ぶ
- その場で動きを見る
- 条件を変えて比較する
- 動画で残す

という、遊べる解析ツールになりました。

二重振り子は、数式として見ても面白いですが、カオスマップから初期値を拾って実際の運動を見るとかなり直感的です。

まだ詰めたいところはありますが、ひとまず

- どこが荒れやすいかを見る
- その場でシミュレータへ渡す
- 条件を変えてさらに試す

という流れはだいぶやりやすくなりました。

コード全体を見たい場合は、リポジトリ本体からたどるのが一番分かりやすいです。

- GitHub リポジトリ: https://github.com/nobunora/double-pendulum-playground
- カオスマップ本体: https://github.com/nobunora/double-pendulum-playground/blob/main/double_pendulum_chaos_map.py
- 2D シミュレータ本体: https://github.com/nobunora/double-pendulum-playground/blob/main/double_pendulum.py
- 任意角度ピッカー: https://github.com/nobunora/double-pendulum-playground/blob/main/double_pendulum_theta_picker.py

# 11. 参考にしたページ・近い事例

- 工学院大学 金丸研究室「二重振り子」
  - https://brain.cc.kogakuin.ac.jp/~kanamaru/Chaos/DP/
  - 二重振り子がカオスの例としてどう見えるかを、かなり素直に説明していて分かりやすいページです。
- 千葉大学サイエンスプロムナード「二重振り子」
  - https://sci-pro.faculty.gs.chiba-u.jp/home/exhibition/huriko
  - 初期状態を少し変えるだけで動きが大きく変わる、という体験寄りの説明が近いです。
- NGKサイエンスサイト「〖二重振り子〗カオスな動きの体操人形」
  - https://site.ngk.co.jp/lab/no191/
  - 二重振り子を工作として体験できるページで、まずカオスを眺めて楽しむという方向が近いです。
- 「地惑、わくわく。」2025 シミュレーション班「二重振り子シミュレーション（お試し版）」
  - https://chiwaku-simulation-2025.vercel.app/pendulum
  - 条件をいじりながら動きを見るという点で、今回のシミュレータ側の方向にかなり近いです。
- 京都府立桃山高校 SSH 成果集
  - https://www.kyoto-be.ne.jp/momoyama-hs/mt/ssh/pdf/%E4%BB%A4%E5%92%8C%EF%BC%92%E5%B9%B4%E5%BA%A6%20%E8%87%AA%E7%84%B6%E7%A7%91%E5%AD%A6%E7%A7%91%E3%80%8CGS%E8%AA%B2%E9%A1%8C%E7%A0%94%E7%A9%B6%E3%80%8D%E6%88%90%E6%9E%9C%E9%9B%86.pdf
  - 二重振り子の角度を変えながらシミュレーションと実機を比べていて、条件を振って違いを見る発想が近いです。
- 「カオス時系列解析の基礎 with R」
  - https://saltcooky.hatenablog.com/entry/2023/10/30/222253
  - FTLEそのものではないですが、最大リャプノフ指数の考え方を日本語で追うのに分かりやすいページです。

# 付録. FTLE とは何か

最後に、記事中で何度も出てきた FTLE について少しだけ丁寧に書いておきます。

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
