from datetime import datetime


def create_command():
    current_time_key = "current_time"

    async def command(state, runtime):
        # 取一次本地时间，保证路由判断和写入 State 使用同一个时间点。
        now = datetime.now()
        second_unit = now.second % 10

        if second_unit <= 3:
            branch = "first"
        elif second_unit <= 6:
            branch = "second"
        else:
            branch = "last"

        return {
            "activate": [branch],
            "update": {
                "shared_vars": {
                    current_time_key: now.isoformat(timespec="seconds"),
                }
            },
        }

    return command
