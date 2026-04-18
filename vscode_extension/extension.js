// Lucy Code VS Code Extension
// Launches the Lucy Code LSP server and provides AI-powered coding assistance

const vscode = require('vscode');
const { LanguageClient, TransportKind } = require('vscode-languageclient/node');

let client = null;
let statusBarItem = null;

function activate(context) {
    console.log('Lucy Code extension activated');

    // Status bar
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.text = '$(sparkle) Lucy Code';
    statusBarItem.tooltip = 'Lucy Code AI Assistant';
    statusBarItem.command = 'lucy.ask';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Start LSP server
    const config = vscode.workspace.getConfiguration('lucy');
    if (config.get('autoStart', true)) {
        startServer(context);
    }

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('lucy.ask', () => askLucyCode(context)),
        vscode.commands.registerCommand('lucy.fix', () => fixWithLucyCode()),
        vscode.commands.registerCommand('lucy.refactor', () => refactorWithLucyCode()),
        vscode.commands.registerCommand('lucy.explain', () => explainWithLucyCode()),
        vscode.commands.registerCommand('lucy.test', () => testWithLucyCode()),
        vscode.commands.registerCommand('lucy.startServer', () => startServer(context)),
    );
}

function startServer(context) {
    const config = vscode.workspace.getConfiguration('lucy');
    const pythonPath = config.get('pythonPath', 'python3');

    const serverOptions = {
        command: pythonPath,
        args: ['-m', 'lucy', '--lsp'],
        transport: TransportKind.stdio,
    };

    const clientOptions = {
        documentSelector: [{ scheme: 'file' }],
        synchronize: {
            fileEvents: vscode.workspace.createFileSystemWatcher('**/*'),
        },
    };

    client = new LanguageClient(
        'lucy',
        'Lucy Code Language Server',
        serverOptions,
        clientOptions,
    );

    client.start();
    statusBarItem.text = '$(sparkle) Lucy Code ✓';
    context.subscriptions.push(client);
}

async function askLucyCode() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        // Open input box for free-form question
        const question = await vscode.window.showInputBox({
            prompt: 'Ask Lucy Code...',
            placeHolder: 'What would you like help with?',
        });
        if (question) {
            await executeCommand('lucy.ask', [question]);
        }
        return;
    }

    const selection = editor.selection;
    const selectedText = editor.document.getText(selection);

    if (selectedText) {
        const question = await vscode.window.showInputBox({
            prompt: 'Ask about this code...',
            placeHolder: 'What would you like to know?',
        });
        if (question) {
            await executeCommand('lucy.ask', [
                editor.document.uri.toString(),
                { start: selection.start, end: selection.end },
                question,
            ]);
        }
    } else {
        const question = await vscode.window.showInputBox({
            prompt: 'Ask Lucy Code...',
            placeHolder: 'What would you like help with?',
        });
        if (question) {
            await executeCommand('lucy.ask', [question]);
        }
    }
}

async function fixWithLucyCode() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;
    await executeCommand('lucy.fix', [
        editor.document.uri.toString(),
        { start: editor.selection.start, end: editor.selection.end },
    ]);
}

async function refactorWithLucyCode() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;

    const instruction = await vscode.window.showInputBox({
        prompt: 'How should this code be refactored?',
        placeHolder: 'e.g., Extract to function, simplify logic...',
    });

    if (instruction) {
        await executeCommand('lucy.refactor', [
            editor.document.uri.toString(),
            { start: editor.selection.start, end: editor.selection.end },
            instruction,
        ]);
    }
}

async function explainWithLucyCode() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;
    await executeCommand('lucy.explain', [editor.document.uri.toString()]);
}

async function testWithLucyCode() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;
    await executeCommand('lucy.test', [editor.document.uri.toString()]);
}

async function executeCommand(command, args) {
    if (client && client.isRunning()) {
        try {
            const result = await client.sendRequest('workspace/executeCommand', {
                command,
                arguments: args,
            });
            if (result && result.message) {
                vscode.window.showInformationMessage(result.message);
            }
        } catch (err) {
            vscode.window.showErrorMessage(`Lucy Code: ${err.message}`);
        }
    } else {
        vscode.window.showWarningMessage('Lucy Code server is not running. Starting...');
    }
}

function deactivate() {
    if (client) {
        return client.stop();
    }
}

module.exports = { activate, deactivate };
