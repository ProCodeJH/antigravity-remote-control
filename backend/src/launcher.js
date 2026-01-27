/**
 * Antigravity Remote Controller - Launcher
 * One-Click Start with QR Code Display (Fixed)
 */

const config = require('./config');
const { startServer } = require('./server');
const tunnelManager = require('./tunnel-manager');
const windowManager = require('./window-manager');
const qrcode = require('qrcode-terminal');

async function displayBanner() {
    console.log(`
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║     █████╗ ███╗   ██╗████████╗██╗ ██████╗ ██████╗  █████╗     ║
║    ██╔══██╗████╗  ██║╚══██╔══╝██║██╔════╝ ██╔══██╗██╔══██╗    ║
║    ███████║██╔██╗ ██║   ██║   ██║██║  ███╗██████╔╝███████║    ║
║    ██╔══██║██║╚██╗██║   ██║   ██║██║   ██║██╔══██╗██╔══██║    ║
║    ██║  ██║██║ ╚████║   ██║   ██║╚██████╔╝██║  ██║██║  ██║    ║
║    ╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝    ║
║                                                               ║
║                   🌐 REMOTE CONTROLLER 🌐                      ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
  `);
}

function displayConnectionInfo(localUrl, publicUrl) {
    console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log('\n📡 CONNECTION INFO\n');

    console.log('Local Network:');
    console.log(`   ${localUrl}`);

    if (publicUrl) {
        console.log('\n🌐 Public URL (use from anywhere):');
        console.log(`   ${publicUrl}`);

        console.log('\n📱 Scan QR Code with your phone:\n');
        qrcode.generate(publicUrl, { small: true });
    } else {
        console.log('\n⚠️  Tunnel not connected - Local access only');
    }

    console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log(`\n🔐 Access PIN: ${config.auth.accessPin}`);
    console.log('\n💡 Tips:');
    console.log('   • Use the PIN to authenticate on your mobile device');
    console.log('   • Swipe left/right to switch between windows');
    console.log('   • Press Ctrl+C to stop the server');
    console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
}

async function main() {
    try {
        await displayBanner();

        console.log('\n⏳ Starting server...');

        // Start the server
        const { port } = await startServer();
        const localUrl = `http://localhost:${port}`;

        console.log(`✓ Server started on port ${port}`);

        // Create initial window
        console.log('\n⏳ Creating initial Antigravity window...');
        const initialWindow = windowManager.createWindow({ name: 'Main Terminal' });
        console.log(`✓ Window created: ${initialWindow.name}`);

        // Start tunnel
        let publicUrl = null;
        console.log('\n⏳ Connecting to ngrok tunnel...');

        try {
            publicUrl = await tunnelManager.connect(port);
            console.log(`✓ Tunnel connected!`);
        } catch (error) {
            console.log(`✗ Tunnel connection failed: ${error.message}`);
            console.log('  Continuing in local-only mode.');
        }

        // Display connection info
        displayConnectionInfo(localUrl, publicUrl);

    } catch (error) {
        console.error(`\n✗ Launch failed: ${error.message}`);
        console.error(error.stack);
        process.exit(1);
    }
}

// Handle cleanup
process.on('SIGINT', async () => {
    console.log('\n\n⏳ Shutting down...');

    try {
        await tunnelManager.disconnect();
        windowManager.destroyAll();
        console.log('✓ Cleanup complete');
    } catch (error) {
        console.error(`✗ Cleanup error: ${error.message}`);
    }

    process.exit(0);
});

main();
