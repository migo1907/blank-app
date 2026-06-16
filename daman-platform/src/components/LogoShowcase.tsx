import DamanLogo from './DamanLogo';

export default function LogoShowcase() {
  return (
    <div className="w-full">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
        <div className="bg-white p-12 rounded-xl shadow-lg border-2 border-daman-blue-600">
          <h3 className="text-center text-slate-600 mb-8 font-semibold">Light Background</h3>
          <div className="space-y-8">
            <div className="flex items-center justify-center">
              <DamanLogo size="xl" />
            </div>

            <div className="flex items-center justify-center pt-8 border-t border-slate-200">
              <DamanLogo size="lg" />
            </div>

            <div className="flex items-center justify-center pt-8 border-t border-slate-200">
              <DamanLogo size="md" />
            </div>

            <div className="flex items-center justify-center pt-8 border-t border-slate-200">
              <DamanLogo size="sm" />
            </div>
          </div>
        </div>

        <div className="bg-slate-900 p-12 rounded-xl shadow-lg border-2 border-daman-blue-500">
          <h3 className="text-center text-slate-400 mb-8 font-semibold">Dark Background</h3>
          <div className="space-y-8">
            <div className="flex items-center justify-center">
              <DamanLogo size="xl" />
            </div>

            <div className="flex items-center justify-center pt-8 border-t border-slate-700">
              <DamanLogo size="lg" />
            </div>

            <div className="flex items-center justify-center pt-8 border-t border-slate-700">
              <DamanLogo size="md" />
            </div>

            <div className="flex items-center justify-center pt-8 border-t border-slate-700">
              <DamanLogo size="sm" />
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-gradient-to-br from-daman-blue-600 to-daman-blue-700 p-8 rounded-xl text-white text-center">
          <DamanLogo size="lg" className="mx-auto mb-4" />
          <h4 className="font-bold text-lg mb-2">On Brand Colors</h4>
          <p className="text-sm text-daman-blue-100">Logo works on brand backgrounds</p>
        </div>

        <div className="bg-gradient-to-br from-slate-700 to-slate-800 p-8 rounded-xl text-white text-center">
          <DamanLogo size="lg" className="mx-auto mb-4" />
          <h4 className="font-bold text-lg mb-2">High Contrast</h4>
          <p className="text-sm text-slate-300">Maintains visibility on dark surfaces</p>
        </div>

        <div className="bg-white border-2 border-slate-300 p-8 rounded-xl text-center">
          <DamanLogo size="lg" className="mx-auto mb-4" />
          <h4 className="font-bold text-lg mb-2 text-slate-900">Always Clear</h4>
          <p className="text-sm text-slate-600">Professional appearance everywhere</p>
        </div>
      </div>
    </div>
  );
}
