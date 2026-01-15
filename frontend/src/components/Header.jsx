import React from 'react';
import { Shield } from 'lucide-react';

const Header = () => {
    return (
        <header className="mb-10 flex items-center justify-between">
            <div className="flex items-center gap-3">
                <Shield className="w-8 h-8 text-purple-500" />
                <h1 className="text-2xl font-bold tracking-tight bg-gradient-to-r from-white to-neutral-400 bg-clip-text text-transparent">
                    The Smart Guard
                </h1>
            </div>
            <div className="flex items-center gap-2 text-sm text-neutral-400">
                <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                System Online
            </div>
        </header>
    );
};

export default Header;
