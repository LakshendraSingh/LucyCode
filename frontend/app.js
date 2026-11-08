import React, { useState, useEffect } from 'react';
import { render, Box, Text } from 'ink';
import { spawn } from 'child_process';
import readline from 'readline';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '..');
const venvPython = path.join(repoRoot, '.venv', 'bin', 'python');
const pythonBin = fs.existsSync(venvPython) ? venvPython : 'python3';
const App = () => {
    const [messages, setMessages] = useState([]);
    const [currentStream, setCurrentStream] = useState('');
    const [toolStatus, setToolStatus] = useState('');
    const [isQuerying, setIsQuerying] = useState(false);
    useEffect(() => {
        // We launch lucy in print mode with the --ndjson flag.
        const prompt = process.argv[2] || 'Hello, who are you?';
        setIsQuerying(true);
        setMessages([`> ${prompt}`]);
        const lucyProcess = spawn(pythonBin, ['-m', 'lucy', '--print', prompt, '--ndjson'], {
            cwd: repoRoot,
        });
        const rl = readline.createInterface({
            input: lucyProcess.stdout,
            terminal: false,
        });
        rl.on('line', (line) => {
            if (!line.trim())
                return;
            try {
                const event = JSON.parse(line);
                if (event.type === 'text_delta') {
                    setCurrentStream((prev) => prev + event.data.text);
                }
                else if (event.type === 'tool_use_start') {
                    setToolStatus(`Running tool: ${event.data.name}...`);
                }
                else if (event.type === 'tool_use_complete') {
                    setToolStatus(`Tool ${event.data.name} completed.`);
                    setTimeout(() => setToolStatus(''), 2000);
                }
                else if (event.type === 'message' && event.data?.role === 'assistant') {
                    setMessages((prev) => [...prev, currentStream]);
                    setCurrentStream('');
                }
            }
            catch (err) {
                // Not JSON, ignore or log
            }
        });
        lucyProcess.on('close', () => {
            setIsQuerying(false);
            process.exit(0);
        });
        return () => {
            lucyProcess.kill();
        };
    }, []);
    return (React.createElement(Box, { flexDirection: "column", padding: 1 },
        React.createElement(Text, { bold: true, color: "green" }, "LucyCode Ink UI Frontend"),
        React.createElement(Box, { flexDirection: "column", marginY: 1 }, messages.map((msg, idx) => (React.createElement(Text, { key: idx }, msg)))),
        currentStream && (React.createElement(Box, { borderStyle: "round", borderColor: "blue", padding: 1 },
            React.createElement(Text, null, currentStream))),
        toolStatus && (React.createElement(Box, { marginTop: 1 },
            React.createElement(Text, { color: "yellow" },
                "\u26A1 ",
                toolStatus))),
        isQuerying && !toolStatus && !currentStream && (React.createElement(Text, { color: "gray" }, "Thinking..."))));
};
render(React.createElement(App, null));
