import React, { useState, useEffect } from 'react';
import { render, Box, Text } from 'ink';
import { spawn } from 'child_process';
import readline from 'readline';

type Event = {
  type: string;
  data?: any;
  role?: string;
  content?: string;
};

const App = () => {
  const [messages, setMessages] = useState<string[]>([]);
  const [currentStream, setCurrentStream] = useState<string>('');
  const [toolStatus, setToolStatus] = useState<string>('');
  const [isQuerying, setIsQuerying] = useState<boolean>(false);

  useEffect(() => {
    // We launch lucy in print mode with the --ndjson flag.
    // For demo purposes, we pass a hardcoded prompt or process.argv[2]
    const prompt = process.argv[2] || 'Hello, who are you?';
    setIsQuerying(true);
    setMessages([`> ${prompt}`]);

    const lucyProcess = spawn('python3', ['-m', 'lucy', '--print', prompt, '--ndjson'], {
      cwd: process.cwd(),
    });

    const rl = readline.createInterface({
      input: lucyProcess.stdout,
      terminal: false,
    });

    rl.on('line', (line) => {
      if (!line.trim()) return;
      try {
        const event: Event = JSON.parse(line);

        if (event.type === 'text_delta') {
          setCurrentStream((prev) => prev + event.data.text);
        } else if (event.type === 'tool_use_start') {
          setToolStatus(`Running tool: ${event.data.name}...`);
        } else if (event.type === 'tool_use_complete') {
          setToolStatus(`Tool ${event.data.name} completed.`);
          setTimeout(() => setToolStatus(''), 2000);
        } else if (event.type === 'message' && event.data?.role === 'assistant') {
          setMessages((prev) => [...prev, currentStream]);
          setCurrentStream('');
        }
      } catch (err) {
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

  return (
    <Box flexDirection="column" padding={1}>
      <Text bold color="green">LucyCode Ink UI Frontend</Text>
      <Box flexDirection="column" marginY={1}>
        {messages.map((msg, idx) => (
          <Text key={idx}>{msg}</Text>
        ))}
      </Box>

      {currentStream && (
        <Box borderStyle="round" borderColor="blue" padding={1}>
          <Text>{currentStream}</Text>
        </Box>
      )}

      {toolStatus && (
        <Box marginTop={1}>
          <Text color="yellow">⚡ {toolStatus}</Text>
        </Box>
      )}

      {isQuerying && !toolStatus && !currentStream && (
        <Text color="gray">Thinking...</Text>
      )}
    </Box>
  );
};

render(<App />);
