public class ClientFolder
{
    public string FolderName { get; set; }      // Subfolder name
    public string Title { get; set; }           // Metadata
    public string Description { get; set; }     // Metadata
    public List<ClientFileRecord> Files { get; set; } = new();
}