using System;
using System.Linq;

namespace Yukino.VRChatAgent
{
    // Exact, local-drive names only. Do not normalize a caller's alias into approval.
    internal sealed class ScriptPathLease
    {
        static void Need(bool ok,string reason){if(!ok)throw new CandidateWriteDenied(reason);}
        internal static void ValidatePath(string path)
        {
            Need(path!=null&&path.Length>=3&&((path[0]>='A'&&path[0]<='Z')||(path[0]>='a'&&path[0]<='z'))&&path[1]==':'&&path[2]=='\\',"local_absolute_path_required");
            if(path.Length==3)return;
            foreach(string part in path.Substring(3).Split('\\'))
            {
                Need(part.Length>0&&part==part.Trim()&&part!="."&&part!=".."&&!part.EndsWith(".",StringComparison.Ordinal)&&
                    !part.Any(c=>char.IsControl(c)||"<>:\"/|?*".Contains(c)),"unsafe_path_component");
                string name=part.Split('.')[0].ToUpperInvariant();
                Need(!(new[]{"CON","PRN","AUX","NUL","CONIN$","CONOUT$"}).Contains(name)&&
                    !(name.Length==4&&(name.StartsWith("COM",StringComparison.Ordinal)||name.StartsWith("LPT",StringComparison.Ordinal))&&"123456789¹²³".Contains(name[3])),"reserved_path");
            }
        }
    }
}
