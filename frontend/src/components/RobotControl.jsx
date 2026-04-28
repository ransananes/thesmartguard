import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import {
    ChevronUp,
    ChevronDown,
    ChevronLeft,
    ChevronRight,
    Circle,
    Cpu,
    Link,
    Link2Off,
    Keyboard,
    Eye,
    EyeOff
} from 'lucide-react';
import { motion } from 'framer-motion';
import toast from 'react-hot-toast';

const RobotControl = ({ isActive = false }) => {
    const [status, setStatus] = useState({ connected: false, port: '' });
    const [isLoading, setIsLoading] = useState(false);
    const [activeCommand, setActiveCommand] = useState(null);
    const [autoFollow, setAutoFollow] = useState(false);

    const fetchStatus = useCallback(async () => {
        try {
            const res = await api.robot.getStatus();
            if (res.success) {
                setStatus(res.status);
            }
        } catch (error) {
            console.error("Failed to fetch robot status", error);
        }
    }, []);

    useEffect(() => {
        fetchStatus();
    }, [fetchStatus]);

    const sendCommand = async (command) => {
        setActiveCommand(command);
        try {
            const res = await api.robot.control(command);
            if (!res.success) {
                toast.error(res.message);
            }
        } catch (error) {
            toast.error("Failed to send command");
        } finally {
            setTimeout(() => setActiveCommand(null), 200);
        }
    };

    const handleConnect = async () => {
        setIsLoading(true);
        try {
            const res = await api.robot.connect();
            if (res.success) {
                toast.success(res.message);
                fetchStatus();
            } else {
                toast.error(res.message);
            }
        } catch (error) {
            toast.error("Connection failed");
        } finally {
            setIsLoading(false);
        }
    };

    const handleDisconnect = async () => {
        setIsLoading(true);
        try {
            const res = await api.robot.disconnect();
            if (res.success) {
                toast.success(res.message);
                fetchStatus();
            } else {
                toast.error(res.message);
            }
        } catch (error) {
            toast.error("Disconnect failed");
        } finally {
            setIsLoading(false);
        }
    };

    const handleToggleFollow = async () => {
        const newState = !autoFollow;
        try {
            const res = await api.robot.toggleFollow(newState);
            if (res.success) {
                setAutoFollow(newState);
                toast.success(res.message);
            } else {
                toast.error(res.message);
            }
        } catch (error) {
            toast.error("Failed to toggle auto-follow");
        }
    };

    useEffect(() => {
        const handleKeyDown = (e) => {
            // Only handle keys when the Robot tab is visible
            if (!isActive) return;
            if (!status.connected) return;

            // Don't intercept keys while the user is typing in a form control
            const tag = document.activeElement?.tagName.toLowerCase();
            if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

            switch (e.key.toLowerCase()) {
                case 'w':
                case 'arrowup':
                    e.preventDefault();
                    sendCommand('F');
                    break;
                case 's':
                case 'arrowdown':
                    e.preventDefault();
                    sendCommand('B');
                    break;
                case 'a':
                case 'arrowleft':
                    e.preventDefault();
                    sendCommand('L');
                    break;
                case 'd':
                case 'arrowright':
                    e.preventDefault();
                    sendCommand('R');
                    break;
                case ' ':
                    e.preventDefault();
                    sendCommand('S');
                    break;
                default:
                    break;
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [status.connected, isActive]);

    const ControlButton = ({ command, icon: Icon, label }) => (
        <motion.button
            whileTap={{ scale: 0.9 }}
            onClick={() => sendCommand(command)}
            disabled={!status.connected}
            className={`
                p-4 rounded-2xl flex flex-col items-center justify-center gap-2 transition-all
                ${!status.connected
                    ? 'bg-neutral-800/30 text-neutral-600 cursor-not-allowed'
                    : activeCommand === command
                        ? 'bg-purple-500 text-white shadow-[0_0_20px_rgba(168,85,247,0.4)]'
                        : 'bg-neutral-800 text-neutral-400 hover:bg-neutral-700 hover:text-white'
                }
            `}
        >
            <Icon size={32} />
            <span className="text-[10px] uppercase tracking-widest font-bold">{label}</span>
        </motion.button>
    );

    return (
        <div className="p-6 space-y-8 h-full">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${status.connected ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                        <Cpu size={20} />
                    </div>
                    <div>
                        <h3 className="font-bold text-white">Robot Status</h3>
                        <p className="text-xs text-neutral-400">
                            {status.connected ? `Connected to ${status.port}` : 'Disconnected'}
                        </p>
                    </div>
                </div>

                <button
                    onClick={status.connected ? handleDisconnect : handleConnect}
                    disabled={isLoading}
                    className={`
                        px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2
                        ${status.connected
                            ? 'bg-neutral-800 text-red-400 hover:bg-red-500/10'
                            : 'bg-purple-600 text-white hover:bg-purple-700 shadow-lg shadow-purple-500/20'
                        }
                    `}
                >
                    {isLoading ? (
                        <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                    ) : status.connected ? (
                        <>
                            <Link2Off size={16} />
                            Disconnect
                        </>
                    ) : (
                        <>
                            <Link size={16} />
                            Connect
                        </>
                    )}
                </button>
            </div>

            <div className="grid grid-cols-3 gap-4 max-w-[300px] mx-auto">
                <div />
                <ControlButton command="F" icon={ChevronUp} label="Forward" />
                <div />

                <ControlButton command="L" icon={ChevronLeft} label="Left" />
                <ControlButton command="S" icon={Circle} label="Stop" />
                <ControlButton command="R" icon={ChevronRight} label="Right" />

                <div />
                <ControlButton command="B" icon={ChevronDown} label="Backward" />
                <div />
            </div>

            <div className="space-y-3">
                <div
                    onClick={handleToggleFollow}
                    className={`
                        p-4 rounded-xl flex items-center justify-between cursor-pointer transition-all border
                        ${autoFollow
                            ? 'bg-purple-600/10 border-purple-500/50 text-purple-400'
                            : 'bg-neutral-800 border-white/5 text-neutral-400 hover:bg-neutral-700'
                        }
                    `}
                >
                    <div className="flex items-center gap-3">
                        {autoFollow ? <Eye size={20} /> : <EyeOff size={20} />}
                        <div>
                            <h4 className="text-sm font-bold">Auto-Follow Person</h4>
                            <p className="text-[10px] opacity-70">Robot follows the largest detected person</p>
                        </div>
                    </div>
                    <div className={`
                        w-10 h-6 rounded-full p-1 transition-colors
                        ${autoFollow ? 'bg-purple-500' : 'bg-neutral-600'}
                    `}>
                        <motion.div
                            animate={{ x: autoFollow ? 16 : 0 }}
                            className="w-4 h-4 bg-white rounded-full"
                        />
                    </div>
                </div>

                <div className="bg-neutral-800/50 rounded-xl p-4 flex items-center gap-4 border border-white/5">
                    <div className="p-2 bg-neutral-900 rounded-lg text-purple-400">
                        <Keyboard size={20} />
                    </div>
                    <div>
                        <h4 className="text-sm font-medium text-white">Keyboard Controls</h4>
                        <p className="text-[11px] text-neutral-500">Use WASD or Arrows to move. Space to stop.</p>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default RobotControl;
