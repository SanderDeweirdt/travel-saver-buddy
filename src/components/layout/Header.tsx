
import React from 'react';
import { Link } from 'react-router-dom';
import UserMenu from '@/components/UserMenu';

const Header = () => {
  return (
    <header className="bg-background border-b border-border h-16 flex items-center px-4 md:px-6">
      <div className="w-full max-w-7xl mx-auto flex justify-between items-center">
        <div className="flex items-center">
          <Link to="/" className="flex items-center">
            <span className="text-xl font-bold">BookingHelper</span>
          </Link>
        </div>
        <UserMenu />
      </div>
    </header>
  );
};

export default Header;
