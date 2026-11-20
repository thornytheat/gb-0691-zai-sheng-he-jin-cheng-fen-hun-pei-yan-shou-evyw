# 接口

`POST /api/run`：JSON中的csv文本，省略使用样例；或multipart字段file。最大5MB。

`POST /api/m1`至`POST /api/m7`：独立运行到指定模块，JSON结构同运行接口。

`GET /api/history`：历史批次。`POST /api/review`接收id、revision和decision（通过或退回）。`GET /api/evidence.csv`提供单一证据导出。

结构错误422，版本变化409，文件过大413；错误返回code与message。所有页面可从左侧七个模块入口访问。

`GET /api/runs/<id>`读取指定批次；页面与证据CSV通过run_id查询参数绑定批次，模块导航保留该参数。

追溯召回（页面`/work/8`）：

`POST /api/trace`：JSON对象，`lot`必填（追溯批号），`run_id`可选（省略取最新批次），`transfers_csv`可选（复配转移记录，表头from_batch,to_batch,lot,mass），`max_steps`可选（正整数，限制本次处理炉次数，用于分步/中断）。同一批次+批号+转移记录复用已有追溯（reused=true），不重复生成召回单。

`POST /api/trace/<id>/resume`：从最近检查点续跑，JSON对象可带`max_steps`；已完成的追溯直接返回原结果。

`GET /api/trace/<id>`：追溯状态、传播路径、各炉处置与判断依据、验收签核快照、召回单。`GET /api/trace/<id>/recalls`仅取召回单。

追溯不存在404；缺批号422；max_steps非正整数422。

JSON请求体必须是对象，数组、标量、null、损坏JSON及错误上传字段返回400，且不运行默认样例。
