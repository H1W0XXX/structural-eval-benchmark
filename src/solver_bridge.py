import json
import os
import tempfile
import multiprocessing
import traceback
from wasmtime import Engine, Store, Module, Linker, WasiConfig, ExitTrap, Config

# 定义一个独立的函数用于在子进程中运行
def _run_wasm_in_process(wasm_path, input_data, return_dict):
    """
    运行在独立子进程中的 WASM 执行逻辑。
    结果写入 return_dict['result'] 或 return_dict['error']
    """
    try:
        # 配置 WASM 引擎 (尝试降低优化等级以规避寄存器分配错误)
        config = Config()
        config.cranelift_opt_level = "none" # 关闭优化，牺牲速度换取稳定性
        
        engine = Engine(config)
        linker = Linker(engine)
        linker.define_wasi()
        
        # 加载模块
        module = Module.from_file(engine, wasm_path)
        store = Store(engine)
        
        input_bytes = json.dumps(input_data).encode("utf-8")

        # 使用临时文件处理 IO
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f_in, \
             tempfile.NamedTemporaryFile(mode='rb', delete=False) as f_out, \
             tempfile.NamedTemporaryFile(mode='rb', delete=False) as f_err:
            
            # 记录文件名以便稍后清理 (注意：子进程内 unlink 可能有权限问题，最好由父进程或最后清理)
            # 但为了简单，我们尽量在 finally 清理
            temp_files = [f_in.name, f_out.name, f_err.name]

            try:
                # 1. 写入输入
                f_in.write(input_bytes)
                f_in.flush()
                f_in.close()

                # 2. 配置 WASI
                wasi = WasiConfig()
                wasi.stdin_file = f_in.name
                wasi.stdout_file = f_out.name
                wasi.stderr_file = f_err.name
                store.set_wasi(wasi)

                # 3. 实例化并运行
                instance = linker.instantiate(store, module)
                start = instance.exports(store)["_start"]
                start(store)

                # 4. 读取结果
                output_bytes = f_out.read()
                if not output_bytes:
                    return_dict['error'] = "Empty Output from WASM"
                else:
                    try:
                        return_dict['result'] = json.loads(output_bytes)
                    except json.JSONDecodeError:
                        return_dict['error'] = "Invalid JSON Output from WASM"

            except ExitTrap as e:
                if e.code != 0:
                    f_err.seek(0)
                    log = f_err.read().decode('utf-8', errors='ignore')
                    return_dict['error'] = f"WASM Crashed (Code {e.code}): {log}"
                else:
                    # Exit 0 可能是正常的，尝试读取输出
                    f_out.seek(0)
                    output_bytes = f_out.read()
                    if output_bytes:
                        try:
                            return_dict['result'] = json.loads(output_bytes)
                        except:
                            return_dict['error'] = "Exit 0 but invalid JSON"
                    else:
                        return_dict['error'] = "Exit 0 with no output"
            
            except Exception as e:
                return_dict['error'] = f"Execution Error: {str(e)}"
            
            finally:
                # 清理文件
                try: f_out.close()
                except: pass
                try: f_err.close()
                except: pass
                
                for f in temp_files:
                    if os.path.exists(f):
                        try: os.unlink(f)
                        except: pass

    except Exception as e:
        return_dict['error'] = f"Process Init Error: {str(e)}\n{traceback.format_exc()}"


class TrussSolver:
    def __init__(self, wasm_path="bin/framecalc.wasm"):
        if not os.path.exists(wasm_path):
            raise FileNotFoundError(f"WASM binary not found at: {wasm_path}")
        self.wasm_path = wasm_path

    def solve(self, input_data: dict, timeout=10):
        """
        通过子进程执行计算，确保主进程安全。
        """
        manager = multiprocessing.Manager()
        return_dict = manager.dict()
        
        # 启动子进程
        p = multiprocessing.Process(
            target=_run_wasm_in_process,
            args=(self.wasm_path, input_data, return_dict)
        )
        
        p.start()
        p.join(timeout=timeout)
        
        if p.is_alive():
            p.terminate()
            p.join()
            return None, f"Timeout ({timeout}s) - Solver process killed"
        
        # 检查退出码
        if p.exitcode != 0:
            # 如果退出码不为0，说明底层崩溃了 (例如 Rust Panic)
            error_msg = return_dict.get('error', f"Process Crashed with exit code {p.exitcode}")
            return None, error_msg
        
        # 正常退出，检查结果
        if 'error' in return_dict:
            return None, return_dict['error']
        
        if 'result' in return_dict:
            return self._clean_floats(return_dict['result']), None
            
        return None, "Unknown Error (No result returned)"

    def _clean_floats(self, data, threshold=1e-9):
        """清洗浮点数"""
        if isinstance(data, dict):
            return {k: self._clean_floats(v, threshold) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._clean_floats(v, threshold) for v in data]
        elif isinstance(data, float):
            return 0.0 if abs(data) < threshold else data
        return data
